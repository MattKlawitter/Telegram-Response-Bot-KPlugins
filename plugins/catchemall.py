import datetime
import json
import os
import pickle
import random
import socket
import threading
from struct import pack, unpack

from plugin import Plugin
from time import sleep


# Called when the bot loads the plugin
# Instantiates this plugin and passes it the bot and plugin directory
def load(data_dir, bot):
    return CatchEmAll(data_dir, bot)


"""
Created by Matthew Klawitter 11/19/2018
Last Updated: 12/1/2018
Version: v1.0.1.1
"""


# Main class of the plugin that handles all commands and interactions
class CatchEmAll(Plugin):
    def __init__(self, data_dir, bot):
        # The directory in which this plugin can store data '/catchemall'
        self.dir = data_dir
        # A reference to the bot itself for more advanced operations
        self.bot = bot
        # A set containing all channels in which to send alerts to
        self.channels = set()
        # A dict object containing all available pokemon encounters
        self.current_encounter = {}
        # A PokeBank object containing data on users and the pokemon they own
        self.poke_bank = PokeBank(self.dir)
        # A PokemonManager object containing data on all pokemon and methods to find information and generate them
        self.poke_manager = PokemonManager(self.dir)
        # A BattleManager object that manages player pokemon parties and helper methods to simulate battles
        self.battle_manager = BattleManager(self.dir)
        # A NPCManager that generates random Trainers and pokemon parties for users to fight
        self.npc_manager = NPCManager(self.dir, self.poke_manager)
        # A List containing all users who have battled an npc since the last encounter. Empties with every new encounter
        self.npc_cooldown = []

        # Launches a deamon thread that handles alerts and random encounters
        thread = threading.Thread(target = self.encounter)
        thread.daemon = True
        thread.start()

    # Adds a pokemon to a specific users personal pokemon bank (self.poke_bank)
    def com_catch(self, command):
        if self.check_miss():
            return "Catch em' All: You missed! Darn it was so close!"

        user = command.user.username
        item = command.args

        # Multi catches are now disabled
        # if ',' in command.args:
        #     commands = command.args.split(",")

        response = "Catch em' All: Congrats {} you caught:\n".format(user)

        if item.lower() in self.current_encounter.keys():
            poke = self.current_encounter.pop(item.lower())
            self.poke_bank.store_mon(user, poke)
            response += "{} (cp:{})!\n".format(poke.name, str(poke.cp))
        return response
        
    def com_fight(self, command):
        user = command.user.username
        item = command.args

        # Multi battles are now disabled
        # if ',' in command.args:
        #     commands = command.args.split(",")

        if self.battle_manager.has_party(user):
            encounter = []
            if item.lower() in self.current_encounter.keys():
                encounter.append(self.current_encounter.pop(item.lower()))

            if len(encounter) > 0:
                battle = Battle(user, "Wild Pokemon")
                party = self.battle_manager.get_party(user)

                response = battle.simulate_battle(party, encounter)
                self.battle_manager.heal_party(party)
                self.poke_bank.save()

                return response
            return "Catch em' All: An encounter does not exist for that pokemon!"
        return "Catch em' All: You have not made a party!"

    # Lists all pokemon within a user's pokemon bank (dict) should they exist
    def com_list(self, command):
        user = command.user.username

        if self.poke_bank.user_exists(user):
            bank = self.poke_bank.user_list(user)
            index = 0
            message = "Here are the contents of {}'s bank\n".format(user)
        
            for pokemon in bank:
                message += str(index) + ": " + pokemon.name + "| cp: " + str(pokemon.cp) + "\n"
                index += 1
            return message
        return "Catch em' All: You do not possess an account!"

    # Releases a pokemon from a users bank given a specific location within the bank (users find locations with /poke_list)
    def com_release(self, command):
        commands = command.args.split(" ")

        if len(commands) == 1: 
            user = command.user.username

            if self.poke_bank.user_exists(user):
                if int(commands[0]) < 0:
                    return "Catch em' All: Please enter a non-negative index value!"
                poke = self.poke_bank.get_mon(user, int(commands[0]))
                if not poke == None:
                    self.poke_bank.remove_mon(user, int(commands[0]))
                    return "Catch em' All: You have released your {} (cp:{})... goodbye...".format(poke.name, str(poke.cp))
                return "Catch em' All: The location you specified does not exist!"
            return "Catch em' All: You do not possess an account!"
        return "Catch em' All: Invalid syntax - use /poke_list [bank_id]"

    # Shows stats of a specified pokemon within a users bank (users find locations with /poke_list)
    def com_stat(self, command):
        commands = command.args.split(" ")

        if len(commands) == 1: 
            user = command.user.username

            if self.poke_bank.user_exists(user):
                if int(commands[0]) < 0:
                    return "Catch em' All: Please enter a non-negative index value!"
                poke = self.poke_bank.get_mon(user, int(commands[0]))
                if not poke == None:
                    return poke.__str__()
                return "Catch em' All: The location you specified does not exist!"
            return "Catch em' All: You do not possess an account!"
        return "Catch em' All: Invalid syntax - use /poke_stat [bank_id]"

    # A simple implementation of trading
    def com_trade(self, command):
        user = command.user.username
        commands = command.args.split(" ")

        if len(commands) == 2: 
            receiver = commands[0]
            bank_index = commands[1]

            try:
                bank_index = int(bank_index)
            except ValueError:
                return "Catch em' All: Invalid syntax - [bank_id] must be an integer!" 

            if self.poke_bank.user_exists(receiver):
                poke = self.poke_bank.remove_mon(user, int(bank_index))
                
                if not poke == None:
                    self.poke_bank.store_mon(receiver, poke)
                    return "Catch em' All: Traded {} to {}!".format(poke.name, receiver)
                return "Catch em' All: The specified pokemon does not exist in your bank!"
            return "Catch em' All: The specified receiver does not have a bank"
        return "Catch em' All: Invalid syntax - use /poke_trade [user] [bank_id]"

    # Admin command to grant pokemon to specific users
    def com_grant(self, command):
        user = command.user.username
        commands = command.args.split(" ")

        if len(commands) == 2: 
            if user == "Klawk":
                if self.poke_manager.find_pokemon(commands[1]):
                    self.poke_bank.store_mon(commands[0], self.poke_manager.generate_exact_pokemon(commands[1]))
                    return "Catch em' All: Granted {} the pokemon {}!".format(commands[0], commands[1])
                return "Catch em' All: Sorry, that pokemon does not exist!"
            return "Catch em' All: Sorry, you are not authorized to use this command!"
        return "Catch em' All: Invalid syntax - use /poke_stat [bank_id]"

    # Admin command to grant a pokemon of a certain level to a specific user
    def com_grant_level(self, command):
        user = command.user.username
        commands = command.args.split(" ")

        if len(commands) == 3: 
            if user == "Klawk":
                if self.poke_manager.find_pokemon(commands[1]):
                    poke = self.poke_manager.generate_exact_pokemon(commands[1])
                    poke.force_level(int(commands[2]))
                    self.poke_bank.store_mon(commands[0], poke)
                    return "Catch em' All: Granted {} the pokemon {}!".format(commands[0], commands[1])
                return "Catch em' All: Sorry, that pokemon does not exist!"
            return "Catch em' All: Sorry, you are not authorized to use this command!"
        return "Catch em' All: Invalid syntax - use /poke_stat [bank_id]"

    # Forms a pokemon party
    def com_form_party(self, command):
        user = command.user.username
        commands = command.args.split(",")

        if 0 < len(commands) <= 6:
            poke_list = []
            
            for index in list(set(commands)):
                poke = self.poke_bank.get_mon(user, int(index))

                if not poke == None:
                    poke_list.append(poke)
                else:
                    return "Catch em' All: Failed! One or more pokemon do not exist in your bank!"

            if self.battle_manager.form_party(user, poke_list):
                return "Catch em' All: Successfully created the party!"
            return "Catch em' All: Failed to created the party! Pokemon specified must be between 0 and 6!"
        return "Catch em' All: Invalid syntax - use /poke_form_party [id1,id2,id3,etc.]"

    # Views a user's currently set pokemon party
    def com_view_party(self, command):
        user = command.user.username
        return self.battle_manager.view_party(user)
    
    # Posts a request to battle an opponent
    def com_post(self, command):
        user = command.user.username
        commands = command.args.split(" ")

        if len(commands) == 1:
            opponent = commands[0]

            if user == opponent:
                return "Catch em' All: You cannot battle yourself!"

            if self.battle_manager.post_battle(user, opponent):
                response = "Catch em' All: Successfully posted a request to battle {}!\n".format(opponent)
                response += "{} you can use '/poke_accept_battle {}' to accept the battle!".format(opponent, user)
                return response
            return "Catch em' All: Unable to create battle! You have already posted an existing battle"
        return "Catch em' All: Invalid syntax - use /poke_post [opponent_name]"

    # Removes a request to battle an opponent
    def com_rm_post(self, command):
        user = command.user.username
        
        if self.battle_manager.remove_battle(user):
            return "Catch em' All: Successfully removed your posted battle!"
        return "Catch em' All: Unable to remove your posted battle! You have not created one!"

    # Accepts a request to battle an opponent and simulates the battle
    def com_accept_battle(self, command):
        user = command.user.username
        commands = command.args.split(" ")

        if len(commands) == 1:
            challenger = commands[0]
            response = self.battle_manager.accept_battle(user, challenger)
            self.poke_bank.save()
            return response
        return "Catch em' All: Invalid syntax - use /poke_accept_battle [challenger_name]"

    # If the user has a party, they then battle an npc based on a provided difficulty
    def com_battle_npc(self, command):
        user = command.user.username

        if user in self.npc_cooldown:
            return "Catch em' All: It's too soon to battle again! Wait until another wild encounter appears!"

        if not command.args == None:
            difficulty = int(command.args)
            npc = self.npc_manager.generate_npc(difficulty)

            if self.battle_manager.has_party(user):
                battle = Battle(user, npc.name)
                self.npc_cooldown.append(user)
                response = battle.simulate_battle(self.battle_manager.get_party(user), npc.party)
                self.battle_manager.heal_party(self.battle_manager.get_party(user))
                return response
            return "Catch em' All: You have not made a party"
        return "Catch em' All: Invalid syntax - use /poke_battle_npc [0-7]"

    # Randomly creates a pokemon encounter and alerts all available chat channels
    def encounter(self):
        sleep(20)
        while threading.main_thread().is_alive():
            spawn_time = random.randint(300,2400)
            response = "Catch em' All: There are wild pokemon about!:\n"

            if len(self.current_encounter.keys()) < 10:
                rand_spawn = random.randint(3,6)
            
                for x in range(rand_spawn):
                    poke = self.poke_manager.generate_pokemon()
                    poke.force_level(random.randint(0,15))
                    self.current_encounter[poke.name.lower()] = poke

            for name in self.current_encounter.keys():
                poke = self.current_encounter[name]
                response += "{} (cp:{})\n".format(poke.name, str(poke.cp))

            self.npc_cooldown.clear()

            for channel in self.channels:
                self.bot.send_message(channel, response)
            sleep(spawn_time)

    # Determines if a user missed a catch
    def check_miss(self):
        r = random.randint(0,100)
        return r <= 10

    # Run whenever someone on telegram types one of these commands
    def on_command(self, command):
        if command.command == "poke_enable":
            if command.chat.id in self.channels:
                return {"type": "message", "message": "This channel is already enabled for encounters."}
            else:
                self.channels.add(command.chat.id)
                return {"type": "message", "message": "Enabled encounters for this channel."}
        elif command.command == "poke_disable":
            if command.chat.id in self.channels:
                self.channels.remove(command.chat.id)
                return {"type": "message", "message": "Disabled encounters for this channel."}
            else:
                return {"type": "message", "message": "Encounters have not been enabled for this channel."}
        elif command.command == "catch":
            return {"type": "message", "message": self.com_catch(command)}
        elif command.command == "fight":
            return {"type": "message", "message": self.com_fight(command)}
        elif command.command == "poke_list":
            return {"type": "message", "message": self.com_list(command)}
        elif command.command == "poke_release":
            return {"type": "message", "message": self.com_release(command)}
        elif command.command == "poke_stat":
            return {"type": "message", "message": self.com_stat(command)}
        elif command.command == "poke_trade":
            return {"type": "message", "message": self.com_trade(command)}
        elif command.command == "poke_grant":
            return {"type": "message", "message": self.com_grant(command)}
        elif command.command == "poke_form_party":
            return {"type": "message", "message": self.com_form_party(command)}
        elif command.command == "poke_view_party":
            return {"type": "message", "message": self.com_view_party(command)}
        elif command.command == "poke_post":
            return {"type": "message", "message": self.com_post(command)}
        elif command.command == "poke_rm_post":
            return {"type": "message", "message": self.com_rm_post(command)}
        elif command.command == "poke_accept_battle":
            return {"type": "message", "message": self.com_accept_battle(command)}
        elif command.command == "poke_battle_npc":
            return {"type": "message", "message": self.com_battle_npc(command)}
        elif command.command == "poke_grant_level":
            return {"type": "message", "message": self.com_grant_level(command)}

    # Commands that are enabled on the server. These are what triggers actions on this plugin
    def get_commands(self):
        return {"poke_enable", "poke_disable", "catch", "fight", "poke_list", "poke_release", "poke_stat",\
                "poke_trade", "poke_grant", "poke_form_party", "poke_view_party", "poke_post",\
                "poke_rm_post", "poke_accept_battle", "poke_battle_npc", "poke_grant_level"}

    # Returns the name of the plugin
    def get_name(self):
        return "Catch em' All"

    # Run whenever someone types /help catchemall
    def get_help(self):
        return "/poke_enable to enable alerts in this channel\n" \
        "/poke_disable to disable alerts in this channel\n" \
        "/catch [poke_name] to catch a pokemon\n" \
        "/fight [poke_name] to fight the current encounter\n" \
        "/poke_list to see pokemon you've caught and their id\n" \
        "/poke_release [bank_id] to release a pokemon\n" \
        "/poke_stat [bank_id] to view stats on a pokemon\n" \
        "/poke_trade [receiver] [bank_id] to trade a pokemon\n" \
        "/poke_grant [user] [pokemon] admin command to grant pokemon\n" \
        "/poke_form_party [id1,id2,id3,etc.] to create a party\n" \
        "/poke_view_party to view a created party\n" \
        "/poke_post [opponent_name]\n" \
        "/poke_rm_post\n" \
        "/poke_accept_battle [challenger_name]\n"\
        "/poke_battle_npc [difficulty between 0-7]"


# Handles methods to generate and battle npcs
class NPCManager:
    def __init__(self, dir, poke_manager):
        self.dir = dir
        self.poke_manager = poke_manager

    def generate_npc(self, difficulty):
        return NPC(self.generate_name(difficulty), self.generate_party(difficulty))

    def generate_name(self, difficulty):
        prefix = []
        name = []

        if difficulty == 0:
            prefix = ["Youngster", "Bug-Catcher", "Lass", "Lad"]
            name = ["Joey", "Jill", "Bob", "Sally", "Sandy", "Larry"]
        elif difficulty == 1:
            prefix = ["Breeder", "Hiker", "Fisherman", "Coder", "Businessman", "Tuber"]
            name = ["Tom", "Geralt", "Terry", "Mark", "Rowan", "Missy", "Alice", "Sue"]
        elif difficulty == 2:
            prefix = ["Punk", "Guitarist", "Sky-Pirate", "Sailor", "Seafarer", "Challenger", "Principle"]
            name = ["Lewis", "Clarney", "Hannah", "Kim", "Braden", "Brad", "Chad", "Stacey"]
        elif difficulty == 3:
            prefix = ["Rocket-Grunt", "Leader", "Gym-Leader", "Ace-Trainer", "Bryce-Look-Alike"]
            name = ["Bill", "Bruce", "Kurt", "Sean", "Trisha", "Jessie", "James", "Watts", "Louise", "Lois", "Elane"]
        elif difficulty == 4:
            prefix = ["Executive", "Director", "Elite", "Chairman"]
            name = ["Giovanni", "Jerry", "Cyrus", "Courtney"]
        elif difficulty == 5:
            prefix = ["Elite-Four", "Frontier-Master", "Rival"]
            name = ["Paul", "Gary", "Lorelei", "Bruno", "Agatha", "Lance"]
        elif difficulty == 6:
            prefix = ["Champion", "Master"]
            name = ["Red", "Blue", "Steven", "Wallace", "Cynthia", "Iris", "Diantha"]
        elif difficulty == 7:
            prefix = ["Developer", "Neuromancer"]
            name = ["Matthew"]
        else:
            prefix = ["Youngster", "Bug-Catcher", "Lass", "Lad"]
            name = ["Joey", "Jill", "Bob", "Sally", "Sandy", "Larry"]

        return random.choice(prefix) + " " + random.choice(name)

    # Generates a random list of pokemon of varying difficulty and returns it
    # Will be refactored in the future
    def generate_party(self, difficulty):
        party = []

        if difficulty == 0: # Levels 1 - 5
            for x in range(2):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(3,4))
                party.append(poke)
        elif difficulty == 1: # Levels 6 - 12
            for x in range(3):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(7,13))
                party.append(poke)
        elif difficulty == 2: # Levels 13 - 18
            for x in range(4):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(14,19))
                party.append(poke)
        elif difficulty == 3: # Levels 19 - 26
            for x in range(5):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(20,27))
                party.append(poke)
        elif difficulty == 4: # Levels 27 - 32
            for x in range(6):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(28,33))
                party.append(poke)
        elif difficulty == 5: # Levels 33 - 40
            for x in range(6):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(34,41))
                party.append(poke)
        elif difficulty == 6: # Levels 41 - 50
            for x in range(6):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(48,50))
                party.append(poke)
        elif difficulty == 7: # Unfair... 9 level 100 pokemon
            poke = self.poke_manager.generate_exact_pokemon("Eevee")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Espeon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Umbreon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Sylveon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Vaporeon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Flareon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Jolteon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Leafeon")
            poke.force_level(99)
            party.append(poke)

            poke = self.poke_manager.generate_exact_pokemon("Glaceon")
            poke.force_level(99)
            party.append(poke)
        else:
            for x in range(3):
                poke = self.poke_manager.generate_pokemon()
                poke.force_level(random.randint(3,5))
                party.append(poke)
        return party


# Contains information on npc's users can battle
class NPC:
    def __init__(self, name, pokemon_list):
        self.name = name
        self.party = pokemon_list

# Manages pokemon battles and records information on records
class BattleManager:
    def __init__(self, dir):
        self.dir = dir
        self.parties = {}
        self.battles = {}

    # Stores a pokemon party within the dict self.parties, only one party per user
    # Sets the value in the dictionary to a list of 1 to 6 pokemon
    def form_party(self, user, poke_list):
        if 0 < len(poke_list) <= 6:
            self.parties[user] = poke_list
            return True
        return False

    # Returns true if the specified user has created a party
    def has_party(self, user):
        if user in self.parties.keys():
            return True
        return False

    # Returns a string containing all pokemon within a created party if it exists
    def view_party(self, user):
        if self.has_party(user):
            response = "Catch em' All: Here is your current party {}:\n".format(user)
            
            for poke in self.parties[user]:
                response += "{} | cp:{}\n".format(poke.name, str(poke.cp))
            return response
        return "Catch em' All: You have not made a party!"

    # Returns a list containing a user's Pokemon party
    def get_party(self, user):
        if self.has_party(user):
            return self.parties[user]
        return None

    # Posts a request to battle an opponent
    # Only one battle request can be created per user at any given time
    def post_battle(self, user, opponent):
        if not user in self.battles.keys():
            self.battles[user] = Battle(user, opponent)
            return True
        return False

    # Removes a request to battle an opponent
    def remove_battle(self, user):
        if user in self.battles.keys():
            self.battles.pop(user, None)
            return True
        return False

    # Restores a pokemon party to full health
    def heal_party(self, party):
        for poke in party:
            poke.current_hp = poke.max_hp

    # A user accepts a battle request and the battle is then simulated
    def accept_battle(self, user, opponent):
        if opponent in self.battles.keys():
            if self.has_party(user) and self.has_party(opponent):
                battle = self.battles[opponent]

                if battle.opponent == user:
                    # A little confusing since the opponent within a battle object is accepting the challengers battle
                    # The user who made the battle
                    challenger_party = self.parties[opponent]
                    # The user who accepted the battle
                    opponent_party = self.parties[user]
                    # Heal both parties
                    self.heal_party(challenger_party)
                    self.heal_party(opponent_party)
                    # Simulate battle
                    results = battle.simulate_battle(challenger_party, opponent_party)

                    # Heal both parties
                    self.heal_party(challenger_party)
                    self.heal_party(opponent_party)

                    # Remove the battle
                    self.battles.pop(opponent)

                    return results
                return "Catch em' All: You are not the opponent for this battle!"
            return "Catch em' All: Cannot battle! Either you or your opponent has not created a party!"
        return "Catch em' All: A battle with that challenger does not exist!"

# Holds information on battles and simulates them
# challenger is the user who created the battle
# opponent is the user who is being challenged and must choose to accept it
class Battle:
    def __init__(self, challenger, opponent):
        self.challenger = challenger
        self.opponent = opponent

    # Simulates a pokemon battle between two parties
    def simulate_battle(self, challenger_party, opponent_party):
        # Holds the index of the current pokemon used for battle within the chalenger_party list
        challenge_index = 0
        # Holds the index of the current pokemon used for battle within the opponent_party list
        opponent_index = 0
        # Holds a String of the winner of the match
        winner = None
        # Holds a log of everything that occurs within the battle
        battle_log = "The battle between {} and {} commences!\n".format(self.challenger, self.opponent)

        # Checks if the index for both pokemon lists is out of bounds
        # The battle continues until one trainer's index exceeds the length of their pokemon list (i.e. challenger_party or opponent_party)
        while challenge_index < len(challenger_party) and opponent_index < len(opponent_party):
            # The current Pokemon used in battle by the challenger
            challenge_mon = challenger_party[challenge_index]
            # The current Pokemon used in battle by the opponent
            opponent_mon = opponent_party[opponent_index]
            # Determines turn order, who attacks first and who is defending
            current_attacker, current_defender = self.compare_speed(challenge_mon, opponent_mon)
            
            battle_log += "{} sends out {}, while {} sends out {}!\n".format(self.challenger, challenge_mon.name, self.opponent, opponent_mon.name)

            # Battle loop that runs until either the current_hp of either the
            # challenger_mon Pokemon or the opponent_mon is less-than or equal to 0
            while challenge_mon.current_hp > 0 and opponent_mon.current_hp > 0:
                # Checks if the current_defender Pokemon manages to dodge this attack
                if self.check_dodge(current_attacker.attack, current_defender.speed):
                    battle_log += "{} managed to dodge {}'s attack!\n".format(current_defender.name, current_attacker.name)
                    
                    # Checks if after a dodge, the current_defender is able to deal counter damage to the current_attacker
                    if self.check_counter(current_attacker.attack, current_defender.attack):
                        damage = int(self.calculate_damage(current_defender, current_attacker)/2)
                        current_attacker.current_hp -= damage
                        battle_log += "Woah! {} was prepared and countered the attack dealing {} to {}!\n".format(current_defender.name, str(damage), current_attacker.name)
                else:
                    # Since the defender failed to dodge, the current_attacker will deal damage to the current_defender
                    damage = self.calculate_damage(current_attacker, current_defender)

                    # Checks to see if the current_attacker deals a critical blow dealing x2 damage
                    if self.check_crit():
                        battle_log += "Uh oh, {} is charging its power!\n".format(current_attacker.name)
                        damage *= 2
                    
                    current_defender.current_hp -= damage
                    battle_log += "{} deals {} to {}!\n".format(current_attacker.name, str(damage), current_defender.name)

                # Swap attacker and defender for next turn
                temp = current_defender
                current_defender = current_attacker
                current_attacker = temp
            
            # Checks if both pokemon failed during the battle, incrementing both
            # challenge_index and opponent_index
            if challenge_mon.current_hp <= 0 and opponent_mon.current_hp <= 0:
                battle_log += "Oh no, both Pokemon fainted! The Pokemon KO'd each other!\n"
                challenge_index += 1
                opponent_index += 1
            else:
                # Checks if the challengers Pokemon fainted during the battle
                # Grants xp to the opponent's Pokemon and checks to see if it has leveled up
                if challenge_mon.current_hp <= 0:
                    # Opponent pokemon won
                    xp = self.calculate_xp(opponent_mon, challenge_mon)
                    challenge_index += 1
                    battle_log += "{}'s {} fainted! {} gained {} xp!\n".format(self.challenger, challenge_mon.name, opponent_mon.name, str(xp))
                
                    if opponent_mon.grant_xp(xp):
                        battle_log += "Woah! {}'s {} leveled up!\n".format(self.opponent, opponent_mon.name)
                else:
                    # Challenger pokemon won
                    xp = self.calculate_xp(challenge_mon, opponent_mon)
                    opponent_index += 1
                    battle_log += "{}'s {} fainted! {} gained {} xp!\n".format(self.opponent, opponent_mon.name, challenge_mon.name, str(xp))
                    
                    if challenge_mon.grant_xp(xp):
                        battle_log += "Woah! {}'s {} leveled up!\n".format(self.challenger, challenge_mon.name)

            battle_log += "{} has {} pokemon left, while {} has {} pokemon left!\n\n".format(self.challenger, int(len(challenger_party) - challenge_index), self.opponent, int(len(opponent_party) - opponent_index))

        # The battle has concluded
        # Checks to see if both users have run out of usable pokemon, if so it labels this battle as a draw
        if challenge_index == len(challenger_party) and opponent_index == len(opponent_party):
            battle_log += "Both trainers are out of usable pokemon! It's a tie!\n"
            winner = "No one"
        else:
            # Checks if the challenger is out of usable pokemon and labels this battle's winner as the opponent
            if challenge_index == len(challenger_party):
                winner = self.opponent
                battle_log += "{} is out of usable pokemon! They blacked out!\n".format(self.challenger)
            else:
                winner = self.challenger
                battle_log += "{} is out of usable pokemon! They blacked out!\n".format(self.opponent)

        battle_log += "The battle has concluded! {} is the winner!".format(winner)
        return battle_log

    # Calculates damage dealt to a pokemon
    def calculate_damage(self, attacker_poke, reciever_poke):
        damage_scalar = random.randint(2,3)
        return (int(((((2 * attacker_poke.level) / 5) + 2) * 100 * (attacker_poke.attack / reciever_poke.attack)) / 50) + 2) * damage_scalar

    # Calculates xp granted to the winning pokemon after a knockout
    def calculate_xp(self, winning_poke, losing_poke):
        level_diff = losing_poke.level / winning_poke.level
        difficulty_bonus = 1

        for x in range(difficulty_bonus):
            difficulty_bonus += .1

        if difficulty_bonus > 2.5:
            difficulty_bonus = 2.5

        if level_diff < 1:
            difficulty_bonus += 1

        return int(15 * level_diff * difficulty_bonus)

    # Compares two pokemon, returning a tuple that first contains the pokemon with the highest speed
    # and the second containing the pokemon with the lowest speed
    def compare_speed(self, poke1, poke2):
        if poke1.speed >= poke2.speed:
            return poke1, poke2
        return poke2, poke1

    # Checks to see if the attacker pokemon successfully lands a critical hit dealing x2
    def check_crit(self):
        return random.randint(0,99) <= 2

    # Checks to see if the defending pokemon manages to dodge an attack
    # Rolls chance based on defender's speed stat and attacker's attack stat
    # Returns true if the defender succeeds the dodge
    def check_dodge(self, attacker_atk, defender_spe):
        return random.randint(0,int(defender_spe / 3)) >= random.randint(0,attacker_atk)

    # Checks to see if the defending pokemon delivers counter attack damage
    # Rolls chance based on defender's attack stat and attacker's attack stat
    # Returns true if the defender succeeds the counter
    def check_counter(self, attacker_atk, defender_atk):
        return random.randint(0,int(defender_atk / 3)) >= random.randint(0,attacker_atk)
    

# Class that handles all operations involving saving and accessing pokemon for individual users
class PokeBank:
    def __init__(self, dir):
        # String containing the directory of the plugin config
        self.dir = dir
        # Dictionary containing keys of users and a list of all pokemon they own
        self.bank = {}
        # Attempts to load 'catchemall/pokebank.file' into self.bank should it exist
        self.load()

    # Stores a given pokemon into a users bank
    # Creates a bank for the user if one doesn't already exist
    def store_mon(self, user, pokemon):
        if user in self.bank.keys():
            self.bank[user].append(pokemon)
            self.save()
        else:
            self.bank[user] = []
            self.bank[user].append(pokemon)
            self.save()

    # Removes and returns a pokemon obj from a users bank given its location
    # Returns None if the location is out of bounds
    def remove_mon(self, user, location):
        if location < len(self.bank[user]):
            poke = self.bank[user].pop(location)
            self.save()
            return poke
        return None

    # Returns a pokemon obj from the specified location within the list should it exist
    # Returns None if the location is out of bounds
    def get_mon(self, user, location):
        if location < len(self.bank[user]):
            poke = self.bank[user][location]
            return poke
        return None

    # Returns a list of all pokemon in a valid user's bank
    # Returns None if the user does not have a bank
    def user_list(self, user):
        return self.bank[user]

    # Returns true if the user exists in the bank
    def user_exists(self, user):
        if user in self.bank.keys():
            return True
        return False

    # Saves the bank to pokebank.file
    def save(self):
        with open(self.dir + "/pokebank.file", "wb") as f:
            pickle.dump(self.bank, f)
            f.seek(0)
            f.close()

    # Attempts to load an available pokebank.file
    def load(self):
        try:
            if os.path.getsize(self.dir + "/pokebank.file") > 0:
                with open(self.dir + "/pokebank.file", "rb") as f:
                    self.bank = pickle.load(f)
                    f.seek(0)
                    f.close()
            print("Catch em' All: PokeBank file successfully loaded!")
        except FileNotFoundError:
            if not os.path.exists(self.dir):
                os.makedirs(self.dir)

            # Ensures that the pokebank file is created.
            with open(self.dir + "/pokebank.file", "w+") as f:
                f.write("")
                f.seek(0)
                f.close()
            print("Catch em' All: No PokeBank file exists, creating a new one.")


# Manages and generates pokemon
class PokemonManager:
    def __init__(self, dir):
        self.dir = dir
        self.pokemon = self.build_set()

    # Attempts to build a dictionary containing all pokemon and their essential data
    def build_set(self):
        data = {}

        try:
            poke_data = json.load(open(os.path.join(self.dir + "/", "pokedex.json")))

            for item in poke_data:
                name = item["ename"]
                attack = item["base"]["Attack"]
                defense = item["base"]["Defense"]
                max_hp = item["base"]["HP"]
                spc_atk = item["base"]["Sp.Atk"]
                spc_def = item["base"]["Sp.Def"]
                speed = item["base"]["Speed"]
                data[name] = {"name" : name, "base_atk" : attack, "base_def" : defense, "base_hp" : max_hp, "base_spc_atk" : spc_atk, "base_spc_def" : spc_def, "base_spe" : speed}
            return data

        except NotADirectoryError:
            data["missingno"] = {"name" : "???", "base_atk" : 0, "base_def" : 0, "base_hp" : 1}
            return data

    # Returns True if a specifc pokemon exists
    def find_pokemon(self, name):
        if name in self.pokemon.keys():
            return True
        return False

    # Returns a newly randomly generated pokemon
    def generate_pokemon(self):
        keys = list(self.pokemon.keys())
        key = random.choice(keys)
        poke = self.pokemon[key]
        return Pokemon(poke["name"], poke["base_atk"], poke["base_def"], poke["base_hp"], poke["base_spc_atk"], poke["base_spc_def"], poke["base_spe"])

    # Returns a specified newly generated pokemon
    def generate_exact_pokemon(self, name):
        poke = self.pokemon[name]
        return Pokemon(poke["name"], poke["base_atk"], poke["base_def"], poke["base_hp"], poke["base_spc_atk"], poke["base_spc_def"], poke["base_spe"])


# Stores information on a specific pokemon and handles initial generation and increases in stats
class Pokemon:
    def __init__(self, poke_name, base_atk, base_def, base_hp, base_spc_atk, base_spc_def, base_spe):
        # String Name of the pokemon
        self.name = poke_name
        # Int Attack of the pokemon
        self.attack = max(base_atk, base_spc_atk)
        # Int Defence of the pokemon
        self.defence = max(base_def, base_spc_def)
        # Int Hitpoints of the pokemon
        self.max_hp = base_hp
        # Int Speed of the pokemon
        self.speed = base_spe
        # Int The current hitpoints of the pokemon
        self.current_hp = base_hp
        # Bool Flag that determines if the pokemon is fanted or not (if current_hp == 0 this should be True)
        self.is_fainted = False
        # Int Level the pokemon is currently at (levels up at 100 xp)
        self.level = 1
        # Int XP the pokemon currently posseses (resets at 100 xp)
        self.xp = 0
        # Float CP Multiplier
        self.cp_multi = 1 / 100
        # Int Combat Power the pokemon posesses (based off its stats)
        self.cp = 0

        # Modifers that increase the pokemon's designated stats each level by the specified amount
        self.attack_growth_mod = 0
        self.defence_growth_mod = 0
        self.hp_growth_mod = 0
        self.speed_growth_mod = 0

        # Adds noise to pokemon attributes
        self.add_iv_noise()
        # Calculates the combat power of the pokemon
        self.calculate_cp()
        # Calculates the growth mods of the pokemon
        self.calculate_growth_mods()

    # Adds some noise to distinct pokemon attributes
    def add_iv_noise(self):
        self.attack = int((self.attack + random.randint(0,15)) + self.attack * self.cp_multi)
        self.defence = int((self.defence + random.randint(0,15)) + self.defence * self.cp_multi)
        self.max_hp = int((self.max_hp + random.randint(0,15)) + self.max_hp * self.cp_multi)
        self.speed = int((self.speed + random.randint(0,15)) + self.speed * self.cp_multi)
        self.current_hp = self.max_hp

    # Calculates stat growth per pokemon
    def calculate_growth_mods(self):
        stats = [self.attack, self.defence, self.max_hp, self.speed]
        mods = [0,0,0,0]

        for x in range(len(stats)):
            index = stats.index(min(stats))
            stats.pop(index)
            mods[index] = x

        self.attack_growth_mod = mods[0]
        self.defence_growth_mod = mods[1]
        self.hp = mods[2]
        self.speed_growth_mod = mods[3]

    # Increases xp of this pokemon by the provided amount and checks for a level up
    def grant_xp(self, amount):
        self.xp += amount
        return self.check_level_up()

    # Checks if a pokemon is capable of leveling up, if so, it levels it up!
    def check_level_up(self):
        if self.xp >= 100:
            self.update_stats()
            return True
        return False

    # Levels up the pokemon
    # takes int levels - the number of levels to increase the pokemon by
    def force_level(self, levels):
        for x in range(levels):
            self.xp += 100
        self.update_stats()

    # Run every level up to adjust stats
    def update_stats(self):
        for x in range(int(self.xp / 100)):
            self.attack += int(random.randint(1,4) + (self.attack * self.cp_multi)) + self.attack_growth_mod
            self.defence += int(random.randint(1,4) + (self.defence * self.cp_multi)) + self.defence_growth_mod
            self.max_hp += int(random.randint(2,5) + (self.max_hp * self.cp_multi)) + self.hp_growth_mod
            self.speed += int(random.randint(1,3) + (self.speed * self.cp_multi)) + self.speed_growth_mod
            self.level += 1
            self.calculate_cp()
        self.xp = self.xp % 100

    # Calculates the combat power of the pokemon
    def calculate_cp(self):
        self.cp = int((self.attack * (self.defence**.5) * (self.max_hp**.5) * (self.cp_multi)) / 10)

    def __str__(self):
        message = "Catch em' All: Stats for {}\n".format(self.name)
        message += "CP: {}\n".format(str(self.cp))
        message += "Lv: {}\n".format(str(self.level))
        message += "Xp: {}/{}\n".format(str(self.xp), str(100))
        message += "HP: {}/{}\n".format(str(self.current_hp), str(self.max_hp))
        message += "Atk: {}\n".format(str(self.attack))
        message += "Def: {}\n".format(str(self.defence))
        message += "Spe: {}\n".format(str(self.speed))
        return message