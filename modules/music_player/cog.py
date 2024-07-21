from botbase import BotBase

from .player import VoiceSessionHandler, QueueInterface, TRACK_LOAD_FAILED
from .checker import is_player_member, is_voice_connectable

import disnake
from disnake.ext import commands
import logging
import json
from random import choices

from mafic import Track, Playlist, TrackEndEvent, NodePool
from mafic.events import EndReason
from utils.converter import time_format, trim_text


class Music(commands.Cog):
	def __init__(self, bot: BotBase):
		self.bot: BotBase = bot
		self.logger: logging.Logger = logging.getLogger(__name__)
		self.session_id = "".join(choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))

		self.pool = NodePool(self.bot)
		self.bot.loop.create_task(self.load_node())

	async def load_node(self):
		with open("modules/music_player/node.json", 'r') as config:
			data: list = json.loads(config.read())

		for node in data:
			try:
				await self.pool.create_node(
					host=node['host'],
					port=node['port'],
					password=node['password'],
					label=node['label'],
					resuming_session_id=self.session_id
				)
			except Exception as e:
				self.logger.error(f"Đã xảy ra sự cố khi kết nối đến lavalink {node['host']}: {e}")


	@commands.cooldown(1, 5, commands.BucketType.guild)
	@commands.slash_command(
		name="play",
		description="Phát một bài hát trên kênh của bạn",
		options=[
			disnake.Option(
				name="search",
				description="Tên hoặc link bài hát",
				required=True,
				type=disnake.OptionType.string
			)
		]
	)
	@commands.guild_only()
	@is_voice_connectable
	async def play(self, inter: disnake.ApplicationCommandInteraction, search: str):
		await inter.response.defer()

		player: VoiceSessionHandler = inter.author.guild.voice_client
		begined = True

		if player is None:
			player: VoiceSessionHandler = await inter.author.voice.channel.connect(cls=VoiceSessionHandler)
			begined = False

		player.notification_channel = inter.channel

		try:
			result = await player.fetch_tracks(search)
			if isinstance(result, Playlist):
				total_time = 0
				for track in result.tracks:
					player.queue.add(track)
					if not track.stream: total_time += track.length

				thumbnail_track = result.tracks[0]
				embed = disnake.Embed(
					title=trim_text("[Playlist] " + thumbnail_track.title, 32),
					url=thumbnail_track.uri,
					color=0xFFFFFF
				)
				embed.description = f"``{thumbnail_track.source.capitalize()} | {result.tracks.__len__()} bài hát | {time_format(total_time)}`"
				embed.set_thumbnail(result.tracks[0].artwork_url)

			elif isinstance(result, list):
				track: Track = result[0]
				player.queue.add(track)
				embed = disnake.Embed(
					title=trim_text(track.title, 32),
					url=track.uri,
					color=0xFFFFFF
				)
				embed.description = f"`{track.source} | {track.author}"
				if track.stream:
					embed.description += " | 🔴 LIVESTREAM`"
				else:
					embed.description += f" | {time_format(track.length)}`"
				embed.set_thumbnail(track.artwork_url)
			else:
				embed = TRACK_LOAD_FAILED
		except:
			embed = TRACK_LOAD_FAILED
			self.logger.error(f"Đã có lỗi xảy ra khi tìm kiếm bài hát: {search} (ID máy chủ: {inter.guild_id})")
		await inter.edit_original_response(embed=embed)

		if not begined:
			await player._continue()
		else:
			await player.update_controller()

	@commands.cooldown(1, 10, commands.BucketType.guild)
	@commands.slash_command(name="stop", description="Dừng phát nhạc")
	@commands.guild_only()
	@is_player_member
	async def stop(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		await inter.response.defer()
		player.notification_channel = inter.channel
		try:
			await player.disconnect()
			await self.bot.http.delete_message(channel_id=player.message_hook[0], message_id=player.message_hook[1])
		except:
			pass
		await inter.edit_original_response(
			embed=disnake.Embed(
				title="⏹️ Đã dừng phát nhạc",
				color=0x00FFFF
			)
		)

	@commands.cooldown(3, 10, commands.BucketType.guild)
	@commands.slash_command(name="pause", description="Tạm dừng bài hát")
	@commands.guild_only()
	@is_player_member
	async def pause(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		await inter.response.defer()
		player.notification_channel = inter.channel
		if player.paused:
			await player.resume()
			await inter.edit_original_response("Đã tiếp tục phát")
		else:
			await player.pause()
			await inter.edit_original_response(f"Đã tạm dừng bài hát")
		await player.update_controller()


	@commands.cooldown(3, 10, commands.BucketType.guild)
	@commands.slash_command(name="next", description="Phát bài hát tiếp theo")
	@commands.guild_only()
	@is_player_member
	async def next(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		await inter.response.defer()
		player.notification_channel = inter.channel
		await player.next()
		await inter.edit_original_response(
			embed=disnake.Embed(
				title="⏭️ Đã chuyển sang bài hát tiếp theo",
				color=0x00FFFF
			)
		)


	@commands.cooldown(3, 10, commands.BucketType.guild)
	@commands.slash_command(name="prev", description="Phát lại bài hát trước đó")
	@is_player_member
	async def prev(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		await inter.response.defer()
		player.notification_channel = inter.channel
		result = await player.previous()
		if result:
			await inter.edit_original_response(
				embed=disnake.Embed(
					title="⏮️ Đã quay lại bài hát trước đó",
					color=0x00FFFF
				)
			)
		else:
			await inter.edit_original_response(
				embed=disnake.Embed(
					title="⚠️ Không có bài hát nào đã phát trước đó",
					color=0xFFFF00
				)
			)



	@commands.slash_command(name="queue", dm_permission=False)
	async def queue(self, inter):
		pass


	@commands.cooldown(1, 20, commands.BucketType.guild)
	@queue.sub_command(name="show", description="Hiển thị danh sách chờ")
	@is_player_member
	async def show_queue(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		await inter.response.defer()
		if not player.queue.upcoming:
			return await inter.edit_original_response("Không có bài hát trong hàng đợi")

		view = QueueInterface(player=player)
		embed = view.embed

		kwargs = {
			"embed": embed,
			"view": view
		}
		try:
			func = inter.followup.send
			kwargs["ephemeral"] = True
		except AttributeError:
			func = inter.send
			kwargs["ephemeral"] = True

		view.message = await func(**kwargs)

		await view.wait()

	@commands.cooldown(1, 20, commands.BucketType.guild)
	@queue.sub_command(name="clear", description="Xoá danh sách chờ")
	@is_player_member
	async def clear_queue(self, inter: disnake.ApplicationCommandInteraction, player: VoiceSessionHandler):
		player.queue.clear()
		await inter.send(embed=disnake.Embed(
			title="✅ Đã xoá tất cả bài hát trong danh sách chờ",
			color=0x00FF00
		))
		await player.update_controller()


	@commands.Cog.listener()
	async def on_track_end(self, event: TrackEndEvent[VoiceSessionHandler]):
		player = event.player
		reason = event.reason
		if reason == EndReason.FINISHED:
			await player._continue()
		elif reason == EndReason.LOAD_FAILED:
			await player.notification_channel.send(f"Đã có lỗi xảy ra khi tải bài hát {player.queue.current_track.title}")
			self.logger.warning(f"Tải bài hát được yêu cầu ở máy chủ {player.guild.id} thất bại")
			await player.next()


	@commands.Cog.listener()
	async def on_button_click(self, inter: disnake.MessageInteraction):
		if not isinstance(inter.component, disnake.Button):
			pass
		button_id = inter.component.custom_id
		if button_id == "music_previous":
			await self.prev(inter=inter)


		elif button_id == "music_pause":
			await self.pause(inter=inter)

		elif button_id == "music_next":
			await self.next(inter=inter)

		elif button_id == "music_stop":
			await self.stop(inter=inter)