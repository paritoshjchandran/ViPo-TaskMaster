import discord
import asyncio

import vipo_tm_exceptions
from discord import errors as discord_exceptions

import os
from dotenv import load_dotenv
from random import choice
from collections import defaultdict
from copy import copy
from copy import deepcopy
import pymongo


try_again_messages = ["Sorry, I didn't get that...",
                      "That's just a whole bunch of garbage to me.",
                      "So what ??",
                      "Like I know what that means",
                      "tELl mE moRe..."]

DEFAULT_BOT_NAME = "(🤖) ViPo-TaskMaster"
BOTC_PRIVATE_STARTS = "/`"
BOTC_PRIVATE_ENDS = "`\\"
BOTC_TOWN_SQUARE = "Town Square"
DEFAULT_PULL_GRACE_SECS = 12
GRACE_MINIMUM_SECONDS = 3
PRIVATE_COTTAGE_START = "TM-"
DEFAULT_MUTE_REASON = "unspeakable reasons"

"""
Emoji policy
- DO NOT TALK ABOUT GENDER
- DO NOT USE SKIN TONE (JUST STANDARD GOLDEN)
"""

PLAYER_EMOJIS = {
    "alive": "💗",  # Alts = 🤍
    "dead": "💀",
    "storyteller": "📖📜",
    "traveller": "💼",
    "spectator": "!👁",
    "buddhist": "🍁",
    "asleep": "💤",  # 🛌😴💤
}

TOWNSQUARE_STATUS_EMOJIS = {
    "no-game": "🔴",
    "gathering-for-game": "🔶",
    "game-in-progress": "🔵",
}

GAME_PHASE_EMOJIS = {
    "night-time": "🌃Night time🌌",
    "private-time": "🌄Private Convos🌅",
    "public-time": "☀Public☀",
    "nomination-time": "🌇Nominations🌇",
}

"""
  - Timer (Pause during nominations)
  - Show juggles and gambles
"""


class ViPoTaskMaster(discord.Client):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        st_command_map = {
            self.silence_all_but_st: ['silence', 'silencio', 'stfu'],
            self.unmute_all: ['unmuteall'],
            self.pull_back_to_town_square: ['pull'],
            self.normal_timer: ['timer', 'talk'],
            self.start_game: ['start'],
            self.kill_player: ['dead', 'death'],
            self.alive_player: ['live', 'alive'],
            self.traveller: ['travel', 'traveller'],
            self.buddhist: ['newplayer'],
            self.end_game: ['end'],
            self.rename_everyone_on_guild: ['fixallnicks'],
            self.rename_mentions: ['rename'],
            self.private_convo_timer: ['day', 'dawn', 'private'],
            self.public_convo_timer: ['public'],
            self.go_to_night: ['night', 'sleep', 'nightfall'],
            self.talk_timer_with_pull: ['oldday', 'olddawn'],  # Works, but, not clean
            self.mute_for_reason: ['mute'],  # Works, but, not clean
            # self.go_to_private_cottages: ['sleep', 'nightfall'],  # Still in the works
        }
        non_st_command_map = {
            self.unmute_me: ['unmuteme', 'whyunmute'],
            self.gather_for_game: ['gather'],
            self.join_town_square_voice: ['joints'],
        }
        self.message_map = {}
        self.non_st_message_map = {}
        for func, commands in st_command_map.items():
            for command in commands:
                self.message_map[command] = func
        for func, commands in non_st_command_map.items():
            for command in commands:
                self.non_st_message_map[command] = func
        self.message_map.update(self.non_st_message_map)
        self.reply_map = {
            'mute reason': self.update_reason_to_mute,
        }
        self.st_muted_members = defaultdict(set)  # State stored in db
        self.reasoned_muted_members = defaultdict(dict)
        self.waiting_for_reply_on = defaultdict(dict)
        # self.private_cottages_users = defaultdict(dict)
        self.mongo_connection = pymongo.MongoClient(host='db',
                                                    username='vipo-taskmaster',
                                                    password='stay-away-hacker!123')
        # Check for pending games and restore state
        self.open_botc_games = self.mongo_connection.botc.open_botc_games
        self.what_ive_done = self.mongo_connection.bot_state
        self.websocket_connections = {}
        self.restore_state()

    def restore_state(self):
        print('Restoring State...', flush=True)
        servers_with_st_mutes = self.what_ive_done.st_muted.find({})
        for server in servers_with_st_mutes:
            self.st_muted_members[server['guild_id']] = set(server['st_muted_players'])
            print(f"RESTORED ST MUTED = {server['guild_id']}'s players -> {server['st_muted_players']}", flush=True)

    async def on_ready(self):
        for guild in self.guilds:
            print(f"=========================================")
            print(f"Ready on Guild: {guild}")
            await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}")
            print(f"BOT Nick Name: {DEFAULT_BOT_NAME}")
            print(f"Guild members: {len(guild.members)}")
        print(f"=========================================", flush=True)

    async def on_message(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        if (content := message.content).upper().startswith('!TM-'):
            command = content.split(' ')[0][4:].lower()
            if message.author.nick.startswith('(ST)'):  # Same as message.author.display_name
                print(f"Got {command} on {message.author.guild.name}'s {message.channel.name} channel from user *{message.author.nick if message.author.nick else message.author.name}*", flush=True)
                try:
                    # noinspection PyArgumentList
                    await self.message_map[command](message)
                except KeyError:
                    await message.channel.send(choice(try_again_messages))
            else:
                try:
                    # noinspection PyArgumentList
                    await self.non_st_message_map[command](message)
                except KeyError:
                    await message.channel.send(choice(try_again_messages))
        elif message.reference \
                and message.reference.message_id in self.waiting_for_reply_on[guild.id].keys() \
                and message.author.id == self.waiting_for_reply_on[guild.id][message.reference.message_id]["from"]:
            reply_type = self.waiting_for_reply_on[guild.id][message.reference.message_id]['reply_type']
            print(f"Reply type = {reply_type} on {self.reply_map[reply_type]}", flush=True)
            # noinspection PyArgumentList
            await self.reply_map[reply_type](message)

    @staticmethod
    async def old_parse_time_str_to_sec(time_str, channel):
        try:
            minutes = 0
            seconds = 0
            if 'm' in time_str:
                minutes, time_str = time_str.split('m')
            if 's' in time_str:
                seconds, time_str = time_str.split('s')
            return int(minutes) * 60 + int(seconds)
        except (TypeError, ValueError):
            embed = discord.Embed(title="Couldn't parse that time format",
                                  description=f"Try something like `!TM-????? 4m` or `!TM-???? 1m30s 15s`",
                                  colour=discord.Colour.red())
            await channel.send(embed=embed)
            raise AssertionError

    @staticmethod
    async def __func_pull__(source_channels: list[discord.VoiceChannel], target_channel: discord.VoiceChannel):
        for channel in source_channels:
            for member in channel.members:
                print(f"{member.nick if member.nick else member.name} is loitering in {channel.name}...", flush=True)
                await member.move_to(target_channel)

    @staticmethod
    def __parse_time_str_for_timer__(time_str: str) -> (int, int):  # TODO: Improve using regex
        try:
            minutes = 0
            seconds = 0
            if 'm' in time_str:
                minutes, time_str = time_str.split('m')
            if 's' in time_str:
                seconds, time_str = time_str.split('s')
            assert not time_str
            return int(minutes), int(seconds)
        except (TypeError, ValueError, AssertionError):
            raise vipo_tm_exceptions.TimeParseError

    @staticmethod
    async def __func_timer__(minutes: int, seconds: int, guild: discord.Guild, notification: str = '', show_timer: bool = False):
        if show_timer:
            while minutes > 1:
                await guild.me.edit(nick=f"(<{minutes+1 if seconds > 0 else minutes}m)🔖{notification}🔖ViPo BOT Timer"[:32])
                await asyncio.sleep(60)
                minutes = minutes - 1
            seconds = seconds+minutes*60
            while seconds > 0:
                await guild.me.edit(nick=f"({seconds}s)🔖{notification}🔖ViPo BOT Timer"[:32])
                await asyncio.sleep(1)
                seconds = seconds - 1
        else:
            await guild.me.edit(nick=f"(🔖{notification})ViPo BOT Timer"[:32])
            await asyncio.sleep((minutes*60)+seconds)
        await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}"[:32])

    @staticmethod
    async def __func_mute_players_on_channel__(voice_channel: discord.VoiceChannel) -> list[int]:  # Deliberately reduced bot ability to mute on specific VoiceChannel
        async def mute(member):
            if (member.nick and not member.nick.startswith('(ST)')) or member.nick is None:
                await member.edit(mute=True)
                return member.id
        muted_members_ids = await asyncio.gather(*map(mute, voice_channel.members))
        print(f"MUTED {list(muted_members_ids)} ON {voice_channel.name}", flush=True)
        print(f"\t{type(muted_members_ids)} \n\t{type(muted_members_ids[0])}", flush=True)
        # noinspection PyTypeChecker
        return muted_members_ids

    @staticmethod
    async def __func_unmute_players_on_channel__(voice_channel: discord.VoiceChannel, addn_players: list[discord.Member]) -> list[int]:
        async def unmute(member):
            if (member.nick and not member.nick.startswith('(ST)')) or member.nick is None:
                await member.edit(mute=False)
                return member.id
        players_to_unmute = set(voice_channel.members)
        players_to_unmute.update(addn_players)
        unmuted_members_ids = await asyncio.gather(*map(unmute, voice_channel.members))
        print(f"UNMUTED {list(unmuted_members_ids)} ON {voice_channel.name}", flush=True)
        # noinspection PyTypeChecker
        return unmuted_members_ids

    @staticmethod
    async def __func_give_town_square_emoji__(voice_channel: discord.VoiceChannel, emoji: str):
        voice_channel_name: str = deepcopy(voice_channel.name)
        print('INSIDE1', flush=True)
        voice_channel_name = voice_channel_name[1:] if any(map(lambda x: voice_channel_name.startswith(x), TOWNSQUARE_STATUS_EMOJIS.values())) else voice_channel_name
        print('INSIDE2', flush=True)
        voice_channel_name = emoji + voice_channel_name
        print(f'INSIDE3, {voice_channel_name}', flush=True)
        try:
            await voice_channel.edit(name=voice_channel_name)
        except Exception as e:
            print(f"{type(e)} -> {e}...", flush=True)
        print('INSIDE4', flush=True)

    @staticmethod
    def __func_get_rename_desc__(renames_needed: tuple):
        renames_needed = {x[0]: x[1] for x in renames_needed if x[1]}
        rename_desc = ''
        if len(renames_needed) > 0:
            rename_desc = '\nPlease rename the following' + \
                          '\n---------------------------\n' + \
                          '\n'.join(map(lambda x: f"{x[0]}: `{x[1]}`...", renames_needed.items()))
        return rename_desc

    @staticmethod
    async def __func_give_player_start_nick__(member: discord.Member):
        guild_me = member.guild.me
        if member != guild_me:
            member_nick: str = member.nick if member.nick else member.name
            for player_emoji in PLAYER_EMOJIS.values():
                member_nick = member_nick.replace(player_emoji, '')
            if member_nick.startswith('!'):
                member_nick = member_nick.replace('!', PLAYER_EMOJIS['spectator'])
            elif member_nick.startswith('(ST)'):
                member_nick = member_nick.replace('(ST)', f"(ST){PLAYER_EMOJIS['storyteller']}")
            else:
                member_nick = f"{PLAYER_EMOJIS['alive']}{member_nick}"
            try:
                await member.edit(nick=member_nick[:32])
            except discord_exceptions.Forbidden:
                return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_dead_nick__(member: discord.Member):
        member_nick: str = member.nick if member.nick else member.name
        member_nick = member_nick.replace(PLAYER_EMOJIS['alive'], PLAYER_EMOJIS['dead'])
        try:
            await member.edit(nick=member_nick[:32])
        except discord_exceptions.Forbidden:
            return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_live_nick__(member: discord.Member):
        member_nick: str = member.nick if member.nick else member.name
        member_nick = member_nick.replace(PLAYER_EMOJIS['dead'], PLAYER_EMOJIS['alive'])
        try:
            await member.edit(nick=member_nick[:32])
        except discord_exceptions.Forbidden:
            return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_traveller_nick__(member: discord.Member):
        member_nick: str = member.nick if member.nick else member.name
        for player_emoji in PLAYER_EMOJIS.values():
            member_nick = member_nick.replace(player_emoji, '')
        member_nick = PLAYER_EMOJIS['traveller'] + PLAYER_EMOJIS['alive'] + member_nick
        try:
            await member.edit(nick=member_nick[:32])
        except discord_exceptions.Forbidden:
            return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_buddhist_nick__(member: discord.Member):
        member_nick: str = member.nick if member.nick else member.name
        for player_emoji in PLAYER_EMOJIS.values():
            member_nick = member_nick.replace(player_emoji, '')
        if PLAYER_EMOJIS['alive'] in member_nick:
            member_nick = member_nick.replace(PLAYER_EMOJIS['alive'], PLAYER_EMOJIS['alive']+PLAYER_EMOJIS['buddhist'])
        elif PLAYER_EMOJIS['dead'] in member_nick:
            member_nick = member_nick.replace(PLAYER_EMOJIS['alive'], PLAYER_EMOJIS['alive'] + PLAYER_EMOJIS['buddhist'])
        else:
            member_nick = PLAYER_EMOJIS['alive'] + PLAYER_EMOJIS['buddhist'] + member_nick
        try:
            await member.edit(nick=member_nick[:32])
        except discord_exceptions.Forbidden:
            return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_original_nick__(member: discord.Member):
        guild_me = member.guild.me
        if member != guild_me:
            member_nick: str = member.nick if member.nick else member.name
            for player_emoji in PLAYER_EMOJIS.values():
                # print(f"{player_emoji.encode('utf-8')} in {member_nick.encode('utf-8')} = {player_emoji in member_nick}", flush=True)
                member_nick = member_nick.replace(player_emoji, '')
            try:
                await member.edit(nick=member_nick[:32])
            except discord_exceptions.Forbidden:
                return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_spectator_nick__(member: discord.Member):
        guild_me = member.guild.me
        if member != guild_me:
            member_nick: str = member.nick if member.nick else member.name
            for player_emoji in PLAYER_EMOJIS.values():
                member_nick = member_nick.replace(player_emoji, '')
            member_nick = PLAYER_EMOJIS['spectator'] + ' ' + member_nick
            try:
                await member.edit(nick=member_nick[:32])
            except discord_exceptions.Forbidden:
                return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_asleep_nick__(member: discord.Member):
        guild_me = member.guild.me
        if member != guild_me:
            member_nick: str = member.nick if member.nick else member.name
            if not member_nick.endswith(PLAYER_EMOJIS['asleep']):
                member_nick = member_nick[:32-3] + PLAYER_EMOJIS['asleep']
            try:
                await member.edit(nick=member_nick[:32])
            except discord_exceptions.Forbidden:
                return member.mention, member_nick[:32]
        return member.mention, None

    @staticmethod
    async def __func_give_player_awake_nick__(member: discord.Member):
        guild_me = member.guild.me
        if member != guild_me:
            member_nick: str = member.nick if member.nick else member.name
            member_nick = member_nick.replace(PLAYER_EMOJIS['asleep'], '')
            try:
                await member.edit(nick=member_nick[:32])
            except discord_exceptions.Forbidden:
                return member.mention, member_nick[:32]
        return member.mention, None

    # noinspection PyUnusedLocal
    async def on_voice_state_update(self, member: discord.Member, before, after):
        # before_channel: discord.VoiceChannel = before.channel
        after_channel: discord.VoiceChannel = after.channel
        member_nick: str = member.nick if member.nick else member.name
        if after_channel and after_channel.name.startswith(TOWNSQUARE_STATUS_EMOJIS['game-in-progress']):
            if not any(map(lambda x: x in member_nick, PLAYER_EMOJIS.values())):
                (await self.__func_give_player_spectator_nick__(member))
                print(f'GIVEN SPECTATOR NAME TO->{member_nick}', flush=True)

    async def normal_timer(self, message: discord.Message):
        guild = message.author.guild
        try:
            command = [param for param in message.content.strip().split(' ') if param]
            assert 2 <= len(command)
            reason = " ".join(command[2:])
            minutes, seconds = self.__parse_time_str_for_timer__(command[1])
            await self.__func_timer__(minutes, seconds, guild, reason, True)
            embed = discord.Embed(title="Timer's up",
                                  description=f"{reason} timer done...",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
        except AssertionError:
            embed = discord.Embed(title="I didn't get that...",
                                  description=f"Sample `!TM-Timer 4m` or `!TM-Timer 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
        except vipo_tm_exceptions.TimeParseError:
            embed = discord.Embed(title="Couldn't parse that time format",
                                  description=f"Try something like `!TM-????? 4m` or `!TM-????? 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)

    async def pull_back_to_town_square(self, message: discord.Message):
        guild = message.author.guild  # Used too many times below
        channels_pulling_from = []
        town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        for channel in guild.channels:
            if channel.name.startswith(BOTC_PRIVATE_STARTS) and channel.name.endswith(BOTC_PRIVATE_ENDS):
                channels_pulling_from.append(channel)
        await self.__func_pull__(channels_pulling_from, town_square_channel)
        desc = "\n" + '\n'.join(map(lambda chnl: chnl.name, channels_pulling_from))
        embed = discord.Embed(title="Get back HERE, NOW !!!", description=f"Pulled everyone back from:{desc}", colour=discord.Colour.dark_blue())
        await message.channel.send(embed=embed)

    async def silence_all_but_st(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        await message.channel.send(f"Silencing {BOTC_TOWN_SQUARE} now...")
        voice_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        muted_member_ids = (await self.__func_mute_players_on_channel__(voice_channel))
        self.st_muted_members[guild.id].update(muted_member_ids)
        self.what_ive_done.st_muted.update_one({"guild_id": guild.id}, {"$set": {"st_muted_players": list(self.st_muted_members[guild.id])}}, upsert=True)
        embed = discord.Embed(title="Shut up!! All of you... ", description=f"Listen to what the ST has to say...\nSilenced `{voice_channel.name}`...", colour=discord.Colour.dark_red())
        await message.channel.send(embed=embed)

    async def unmute_all(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        await message.channel.send(f"Un-muting {BOTC_TOWN_SQUARE} now...")
        members_to_unmute = []
        for member_id in self.st_muted_members[guild.id]:
            members_to_unmute.append(discord.utils.get(guild.members, id=member_id))
        print(f"GOT {len(members_to_unmute)} members to unmute...", flush=True)
        voice_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        unmuted_members_ids = (await self.__func_unmute_players_on_channel__(voice_channel, members_to_unmute))
        print(f"UNMUTED {len(unmuted_members_ids)} players on {guild.name}...")
        self.st_muted_members[guild.id] = set()
        self.what_ive_done.st_muted.delete_one({"guild_id": guild.id})
        embed = discord.Embed(title="Your turn now", description=f"Speak up...", colour=discord.Colour.dark_green())
        await message.channel.send(embed=embed)

    async def gather_for_game(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        await self.__func_give_town_square_emoji__(town_square_channel, TOWNSQUARE_STATUS_EMOJIS['gathering-for-game'])
        (await town_square_channel.connect()) if guild.me not in town_square_channel.members else None
        await guild.me.edit(nick=f"(🤖) GATHERING for BoTC"[:32])

    async def start_game(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        await self.__func_give_town_square_emoji__(town_square_channel, TOWNSQUARE_STATUS_EMOJIS['game-in-progress'])
        (await town_square_channel.connect()) if guild.me not in town_square_channel.members else None
        renames_needed = await asyncio.gather(*map(self.__func_give_player_start_nick__, town_square_channel.members))
        embed = discord.Embed(title="Game is starting now...",
                              description=self.__func_get_rename_desc__(renames_needed),
                              colour=discord.Colour.blurple())
        await message.channel.send(embed=embed)
        # await self.go_to_night(message)

    async def kill_player(self, message: discord.Message):
        member_mentions = (await asyncio.gather(*map(self.__func_give_player_dead_nick__, message.mentions)))
        embed = discord.Embed(title="The following player(s) died...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
        await message.channel.send(embed=embed)

    async def alive_player(self, message: discord.Message):
        member_mentions = (await asyncio.gather(*map(self.__func_give_player_live_nick__, message.mentions)))
        embed = discord.Embed(title="The following player(s) are now alive...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
        await message.channel.send(embed=embed)

    async def traveller(self, message: discord.Message):
        member_mentions = (await asyncio.gather(*map(self.__func_give_player_traveller_nick__, message.mentions)))
        embed = discord.Embed(title="The following player(s) are now travellers...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
        await message.channel.send(embed=embed)

    async def buddhist(self, message: discord.Message):
        member_mentions = (await asyncio.gather(*map(self.__func_give_player_buddhist_nick__, message.mentions)))
        embed = discord.Embed(title="The following player(s) are now registered as buddhist...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
        await message.channel.send(embed=embed)

    async def end_game(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        await self.__func_give_town_square_emoji__(town_square_channel, TOWNSQUARE_STATUS_EMOJIS['no-game'])
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass
        renames_needed = await asyncio.gather(*map(self.__func_give_player_original_nick__, town_square_channel.members))
        embed = discord.Embed(title="Game Over...",
                              description=self.__func_get_rename_desc__(renames_needed),
                              colour=discord.Colour.blurple())
        await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}"[:32])
        await message.channel.send(embed=embed)

    async def rename_everyone_on_guild(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        renames_needed = await asyncio.gather(*map(self.__func_give_player_original_nick__, guild.members))
        embed = discord.Embed(title="Renamed everyone on guild...",
                              description=self.__func_get_rename_desc__(renames_needed),
                              colour=discord.Colour.blurple())
        await message.channel.send(embed=embed)

    async def rename_mentions(self, message: discord.Message):
        # guild: discord.Guild = message.author.guild  # Used too many times below
        renames_needed = await asyncio.gather(*map(self.__func_give_player_original_nick__, message.mentions))
        embed = discord.Embed(title="Renamed the mentions...",
                              description=self.__func_get_rename_desc__(renames_needed),
                              colour=discord.Colour.blurple())
        await message.channel.send(embed=embed)

    async def private_convo_timer(self, message: discord.Message):
        guild = message.author.guild
        try:
            command = [param for param in message.content.strip().split(' ') if param]
            assert 2 <= len(command) <= 3
            reason = GAME_PHASE_EMOJIS['private-time']
            minutes, seconds = self.__parse_time_str_for_timer__(command[1])
            grace_minutes, grace_seconds = 0, DEFAULT_PULL_GRACE_SECS
            if len(command) < 3:
                command.append(f'{DEFAULT_PULL_GRACE_SECS}s')
            else:
                grace_minutes, grace_seconds = self.__parse_time_str_for_timer__(command[2])
            embed = discord.Embed(title="It's the break of day...",
                                  description=f"Time for private conversations: {command[1]} secs...\nGrace period before pull: {command[2]}...",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
            # town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
            # member_mentions = (await asyncio.gather(*map(self.__func_give_player_awake_nick__, town_square_channel.members)))
            # embed = discord.Embed(title="The following player(s) are now awake...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
            # await message.channel.send(embed=embed)
            await self.__func_timer__(minutes, seconds, guild, reason, True)
            embed = discord.Embed(title="Please come back to Town Square...",
                                  description=f"Time for private conversations is over\nGrace period before pull: {command[2]} secs starts now...",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
            await self.__func_timer__(grace_minutes, grace_seconds, guild, 'GRACE PERIOD', False)
            await guild.me.edit(nick=f"(ENDING GRACE PERIOD)-ViPo BOT"[:32])
            embed = discord.Embed(title="Last 3 seconds of Grace Period",
                                  colour=discord.Colour.red())
            embed.add_field(name='Seconds left to pull', value='3')
            last_count_msg = (await message.channel.send(embed=embed))
            for i in range(GRACE_MINIMUM_SECONDS, -1, -1):
                embed = discord.Embed(title="Last 3 seconds of Grace Period",
                                      colour=discord.Colour.red())
                embed.add_field(name='Seconds left to pull', value=str(i))
                await last_count_msg.edit(embed=embed)
                await asyncio.sleep(1)
            await self.pull_back_to_town_square(message)
            await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}")
        except AssertionError:
            embed = discord.Embed(title="I didn't get that...",
                                  description=f"Sample `!TM-Timer 4m` or `!TM-Timer 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
        except vipo_tm_exceptions.TimeParseError:
            embed = discord.Embed(title="Couldn't parse that time format",
                                  description=f"Try something like `!TM-????? 4m` or `!TM-????? 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)

    async def public_convo_timer(self, message: discord.Message):
        guild = message.author.guild
        try:
            command = [param for param in message.content.strip().split(' ') if param]
            assert 2 <= len(command) < 3
            reason = GAME_PHASE_EMOJIS['public-time']
            minutes, seconds = self.__parse_time_str_for_timer__(command[1])
            embed = discord.Embed(title="Public Conversations Begin...",
                                  description=f"Time for public conversations: {command[1]} secs...",
                                  colour=discord.Colour.blurple())
            await message.channel.send(embed=embed)
            await self.__func_timer__(minutes, seconds, guild, reason, True)
            embed = discord.Embed(title="Public Conversations End...",
                                  description=f"Hope you came out with your theories, because it is *almost* time to make your nominations...",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
            await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}")
        except AssertionError:
            embed = discord.Embed(title="I didn't get that...",
                                  description=f"Sample `!TM-Timer 4m` or `!TM-Timer 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
        except vipo_tm_exceptions.TimeParseError:
            embed = discord.Embed(title="Couldn't parse that time format",
                                  description=f"Try something like `!TM-????? 4m` or `!TM-????? 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)

    async def go_to_night(self, message: discord.Message):
        guild = message.author.guild
        try:
            command = [param for param in message.content.strip().split(' ') if param]
            assert len(command) < 2
            await guild.me.edit(nick=f"({GAME_PHASE_EMOJIS['night-time']})"[:32])
            sleep_rename_members = []
            town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
            for member in town_square_channel.members:
                member_nick = member.nick if member.nick else member.name
                if (PLAYER_EMOJIS['alive'] in member_nick) or (PLAYER_EMOJIS['dead'] in member_nick):
                    sleep_rename_members.append(member)
            member_mentions = (await asyncio.gather(*map(self.__func_give_player_asleep_nick__, sleep_rename_members)))
            embed = discord.Embed(title="The following player(s) are now asleep...", description="\n".join(map(lambda x: x[0], member_mentions)) + self.__func_get_rename_desc__(member_mentions))
            await message.channel.send(embed=embed)
        except AssertionError:
            embed = discord.Embed(title="I didn't get that...",
                                  description=f"Sample `!TM-Timer 4m` or `!TM-Timer 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
        except vipo_tm_exceptions.TimeParseError:
            embed = discord.Embed(title="Couldn't parse that time format",
                                  description=f"Try something like `!TM-????? 4m` or `!TM-????? 1m30s`",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)

    # noinspection PyMethodMayBeStatic
    async def join_town_square_voice(self, message: discord.Message):
        guild = message.author.guild
        town_square_channel: discord.VoiceChannel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        (await town_square_channel.connect()) if guild.me not in town_square_channel.members else None

    # ======= USE THE FUNCTIONS BELOW WITH CAUTION ======\

    # Works, but in bad need of a makeover
    async def mute_for_reason(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        notification_string = ''
        affected_ids = []
        for member in message.mentions:
            await member.edit(mute=True)
            notification_string += f'\n{member.mention}'
            affected_ids.append(member.id)
            # self.reasoned_muted_members[guild.id].update({member.id: {"reason": DEFAULT_MUTE_REASON, "mute_message_id": message.id}})
            self.reasoned_muted_members[guild.id].update({member.id: DEFAULT_MUTE_REASON})
        embed = discord.Embed(title="Mute for a reason...", description=f"Muted the following:{notification_string}\n[Optional]\n{message.author.mention} reply with a reason for this action...")
        print(list(self.reasoned_muted_members[guild.id].keys())[0], flush=True)
        print(type(list(self.reasoned_muted_members[guild.id].keys())[0]), flush=True)
        db_safe_reasoned_mutes = deepcopy(self.reasoned_muted_members[guild.id])
        db_safe_reasoned_mutes = {str(member_id): mute_reason for member_id, mute_reason in db_safe_reasoned_mutes.items()}
        self.what_ive_done.reasoned_muted.update_one({"guild_id": guild.id}, {"$set": {"reasoned_muted_players": db_safe_reasoned_mutes}}, upsert=True)
        reasoned_mute_message = (await message.channel.send(embed=embed))
        waiting_details = {"from": message.author.id, "reply_type": "mute reason", "affects": affected_ids}
        self.waiting_for_reply_on[guild.id].update({reasoned_mute_message.id: waiting_details})
        self.what_ive_done.waiting_for_reply_on.update_one({"guild_id": guild.id}, {"$set": {str(reasoned_mute_message.id): waiting_details}}, upsert=True)

    # Works, but in bad need of a makeover
    async def update_reason_to_mute(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        ref_msg_id = message.reference.message_id
        affected_players = self.waiting_for_reply_on[guild.id][ref_msg_id]['affects']
        for player_id in affected_players:
            print(f"Trying to update reason {message.content} for mute on {player_id} in {message.author.guild}", flush=True)
            self.reasoned_muted_members[guild.id].update({player_id: message.content})
        self.what_ive_done.reasoned_muted.update_one({"guild_id": guild.id}, {"$set": {"reasoned_muted_players": self.reasoned_muted_members[guild.id]}}, upsert=True)

    # Works, but in bad need of a makeover
    async def unmute_me(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        print(f'Trying to unmute using content {message.content}', flush=True)
        for message_id, details in self.waiting_for_reply_on[guild.id].items():
            if details['reply_type'] == 'mute reason' and message.author.id in details['affects']:
                await message.author.edit(mute=False)
                embed = discord.Embed(title=f"Unmuted {message.author.nick}...",
                                      description=f"Claims `{self.reasoned_muted_members[guild.id][message.author.id]}` issues are resolved...")
                await message.channel.send(embed=embed)
                del self.reasoned_muted_members[guild.id][message.author.id]
                self.what_ive_done.reasoned_muted.update_one({"guild_id": guild.id}, {"$set": {"reasoned_muted_players": self.reasoned_muted_members[guild.id]}})
                self.waiting_for_reply_on[guild.id][message_id]['affects'].remove(message.author.id)
                if len(self.waiting_for_reply_on[guild.id][message_id]['affects']) == 0:
                    del self.waiting_for_reply_on[guild.id][message_id]

    # Not yet working
    # noinspection PyMethodMayBeStatic
    async def go_to_private_cottages(self, message: discord.Message):
        guild: discord.Guild = message.author.guild  # Used too many times below
        town_square_channel = discord.utils.find(lambda cnl: BOTC_TOWN_SQUARE in cnl.name, guild.channels)
        st_member = message.author
        private_cottages_available = []
        members_to_be_moved = []
        spectators = []
        for channel in guild.channels:
            if channel.name.startswith(PRIVATE_COTTAGE_START):
                private_cottages_available.append(channel)
        for town_square_member in town_square_channel.members:
            member_name = town_square_member.nick if town_square_member.nick else town_square_member.name
            if not (member_name.startswith('(ST)') or member_name.startswith('!')):
                members_to_be_moved.append(town_square_member)
            elif member_name.startswith('!'):
                spectators.append(town_square_member)
        blanket_overwrites = {member: discord.PermissionOverwrite(connect=False, view_channel=False) for member in members_to_be_moved}
        blanket_overwrites.update({member: discord.PermissionOverwrite(connect=False, view_channel=False) for member in spectators})
        blanket_overwrites.update({st_member: discord.PermissionOverwrite(connect=True, view_channel=True)})
        blanket_overwrites.update({guild.me: discord.PermissionOverwrite(connect=True, view_channel=True)})
        for count, member in enumerate(members_to_be_moved):
            print(f"Need to move {member.nick} to Cottage #{count+1}...", flush=True)
            try:
                cottage_channel = private_cottages_available[count]
                overwrites = copy(blanket_overwrites)
                overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)
                # Enforce channel permissions for other members
                await member.move_to(cottage_channel)
            except IndexError:
                # guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),  # Move this outside for each individual player
                overwrites = copy(blanket_overwrites)
                overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)
                cottage_name = f"{PRIVATE_COTTAGE_START}Cottage #{count+1}"
                cottage_channel = (await guild.create_voice_channel(cottage_name, overwrites=overwrites))
                await member.move_to(cottage_channel)

    # Deprecated
    async def talk_timer_with_pull(self, message: discord.Message):
        # try:
        #
        #     await self.__func_timer__()
        # except AssertionError:
        #     embed = discord.Embed(title="I didn't get that...",
        #                           description=f"Sample `!TM-Talk 4m` or `!TM-Talk 1m30s 15s`\n First for time\n Second param for GracePeriod",
        #                           colour=discord.Colour.red())
        #     await message.channel.send(embed=embed)
        guild = message.author.guild  # Used too many times below
        grace_secs = DEFAULT_PULL_GRACE_SECS
        try:
            command = message.content.strip().split(' ')
            command = [param for param in command if len(param) > 0]
            assert 2 <= len(command) <= 3
            talk_timer_secs = (await self.old_parse_time_str_to_sec(command[1], message.channel))
            if len(command) == 3:
                grace_secs = max((await self.old_parse_time_str_to_sec(command[2], message.channel)), 3)
            embed = discord.Embed(title="It's the break of day...",
                                  description=f"Time for private conversations: {talk_timer_secs} secs...\nGrace period before pull: {grace_secs} secs...",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)
            # await asyncio.sleep(talk_timer_secs)
            for i in range(talk_timer_secs, -1, -1):
                await guild.me.edit(nick=f"({i}s)-ViPo BOT"[:32])
                await asyncio.sleep(1)
            embed = discord.Embed(title="Please come back to Town Square",
                                  description=f"Time for private conversations is over\nGrace period before pull: {grace_secs} secs starts now...",
                                  colour=discord.Colour.red())
            await guild.me.edit(nick=f"(Grace Period)-ViPo BOT"[:32])
            await message.channel.send(embed=embed)
            await asyncio.sleep(grace_secs - GRACE_MINIMUM_SECONDS)
            await guild.me.edit(nick=f"(ENDING GRACE PERIOD)-ViPo BOT"[:32])
            embed = discord.Embed(title="Last 3 seconds of Grace Period",
                                  colour=discord.Colour.red())
            embed.add_field(name='Seconds left to pull', value='3')
            last_count_msg = (await message.channel.send(embed=embed))
            for i in range(GRACE_MINIMUM_SECONDS, -1, -1):
                embed = discord.Embed(title="Last 3 seconds of Grace Period",
                                      colour=discord.Colour.red())
                embed.add_field(name='Seconds left to pull', value=str(i))
                await last_count_msg.edit(embed=embed)
                # await message.channel.edit_message(last_count_msg, embed=embed)
                await asyncio.sleep(1)
            await self.pull_back_to_town_square(message)
            await guild.me.edit(nick=f"{DEFAULT_BOT_NAME}")
        except AssertionError:
            embed = discord.Embed(title="I didn't get that...",
                                  description=f"Sample `!TM-Talk 4m` or `!TM-Talk 1m30s 15s`\n First for time\n Second param for GracePeriod",
                                  colour=discord.Colour.red())
            await message.channel.send(embed=embed)


if __name__ == "__main__":
    load_dotenv()
    intents = discord.Intents.default()
    intents.members = True
    discord_client = ViPoTaskMaster(intents=intents)
    discord_client.run(os.getenv('DISCORD_TOKEN'))
