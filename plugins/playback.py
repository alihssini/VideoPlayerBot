"""Playback commands. Each handler: target group + permission -> player / resolver -> short answer.
All of them work in the group and in the private chat (for the group chosen with /use or '#<number>')."""

from pyrogram.handlers import MessageHandler
from commandmapper import mode_of, tag
from core.acl import Role
from core.errors import UserError
from core.models import AUDIO, VIDEO
from core.player import fmt_time
from core.timeparse import parse_jump
from plugins.common import cmd, require_any, target
from services.lyrics import LyricsUnavailable
from ui.replies import Status, clean, command, say
from ui.texts import USAGE_PLAY


def register(app) -> None:
    player, client = app.player, app.client

    async def _lyrics_for(item, chat_id, status) -> str | None:
        """Turn a resolved song into its lyrics video (in place); returns a note when it stays as it is."""
        if item.kind != AUDIO:
            return "🎤 **Lyrics are for songs**, this one plays as it is."
        await player.prepare(item)
        try:
            path = await app.lyrics.make(chat_id, item.source, item.name, item.duration, item.thumb, item.key, status)
        except LyricsUnavailable as e:
            return f"🎤 **Playing the music only**, {e}."
        item.files.append(path)
        item.source, item.kind, item.lyrics, item.prepare = path, VIDEO, True, None
        return None

    async def _play(m, force=None, lyrics=False):
        t = await target(app, m, Role.SUDO, bare="with_more")
        args, kind = t.args, force
        if args and mode_of(args[0]):
            kind, args = mode_of(args[0]), args[1:]
        query = " ".join(args).strip()
        if not query and not m.reply_to_message:
            raise UserError(USAGE_PLAY)
        if player.queue_full(t.chat_id):
            raise UserError(f"**The queue is full** ({player.max_queue} items)! Use {tag('next')} or wait.")
        eager = not await player.is_playing(t.chat_id)
        async with Status(m) as status:
            item = await app.resolver.resolve(m, t.chat_id, query, kind, status, t.user, eager)
            try:
                if t.dm:
                    item.reply_chat = m.chat.id
                note = await _lyrics_for(item, t.chat_id, status) if lyrics else None
                if eager:
                    await status.update("🔄 `Joining the voice chat ...`")
                position = await player.enqueue(t.chat_id, t.title, item)
            except BaseException:
                player.discard(item)
                raise
            if position == 0:
                await status.done(None)
            else:
                by = f" · 👤 **{clean(t.user.name)}**" if t.user else ""
                await status.done(f"➕ **Added to the queue** (#{position}){t.where}\n`{clean(item.name)}`{by}\n\n"
                                  f"Next: {tag('next')} · list: {tag('queue')}")
            if note:
                await say(m, note)

    @command
    async def play(_, m):
        await _play(m)

    @command
    async def stream(_, m):
        await _play(m, VIDEO)

    @command
    async def lyrics(_, m):
        t = await target(app, m, Role.SUDO, bare="with_more")
        if t.args or m.reply_to_message:
            return await _play(m, AUDIO, lyrics=True)
        state = app.store.peek(t.chat_id)
        if not await player.is_playing(t.chat_id) or not state or not state.playback:
            raise UserError(f"__Send__ {tag('lyrics')} `<song name or link>`__, or send__ {tag('lyrics')} __while a song plays.__")
        item = state.playback.item
        if item.lyrics:
            raise UserError("🎤 **The lyrics are already showing.**")
        if item.kind == VIDEO:
            raise UserError("🎤 **Lyrics are for songs**, this is a video.")
        async with Status(m, "🎤 `Looking for lyrics ...`") as status:
            source = item.source
            try:
                path = await app.lyrics.make(t.chat_id, source, item.name, item.duration, item.thumb, item.key, status)
            except LyricsUnavailable as e:
                return await status.done(f"🎤 **The song keeps playing as it is**, {e}.")
            await player.switch_source(t.chat_id, source, path, VIDEO)
            await status.done(None)

    @command
    async def pause(_, m):
        t = await target(app, m)
        await player.pause(t.chat_id, t.user)
        await say(m, f"⏸ **Paused**{t.where}.")

    @command
    async def resume(_, m):
        t = await target(app, m)
        await player.resume(t.chat_id, t.user)
        await say(m, f"▶️ **Resumed**{t.where}.")

    @command
    async def next_(_, m):
        t = await target(app, m)
        item = await player.skip(t.chat_id, t.user)
        if t.dm:
            await say(m, f"⏭ **Skipped**{t.where}, now: `{clean(item.name)}`")

    @command
    async def end(_, m):
        t = await target(app, m)
        kind, dropped = await player.stop(t.chat_id, t.user)
        extra = f" The queue ({dropped}) was cleared." if dropped else ""
        await say(m, f"⏹ **Stopped**{t.where}.{extra}")

    @command
    async def queue(_, m):
        t = await target(app, m)
        playing = await player.is_playing(t.chat_id)
        state = app.store.peek(t.chat_id)
        items = list(state.queue) if state else []
        if not playing and not items:
            raise UserError(f"**Nothing is playing and the queue is empty**{t.where}.")
        lines = [f"📋 **Queue**{t.where}", ""]
        if playing and state.playback:
            pb = state.playback
            now = f"▶️ **Now:** `{clean(pb.item.name)}` · `{fmt_time(pb.position())}`"
            if pb.item.requested_by:
                now += f" — **{clean(pb.item.requested_by.name)}**"
            lines.append(now)
        if items:
            lines.append("")
            for i, it in enumerate(items, 1):
                by = f" — **{clean(it.requested_by.name)}**" if it.requested_by else ""
                lines.append(f"{i}. {'🎬' if it.kind == VIDEO else '🎵'} `{clean(it.name)}`{by}")
            lines += ["", f"{len(items)}/{player.max_queue} · skip with {tag('next')}"]
        else:
            lines += ["", f"__Nothing queued after this, send__ {tag('play')} __to add more.__"]
        await say(m, "\n".join(lines))

    @command
    async def jump(_, m):
        t = await target(app, m, bare="never")
        parsed = parse_jump("".join(t.args))
        if not parsed:
            raise UserError(f"__How far?__ {tag('jump')} `30` · `+5m` · `-10` · `-40s` · `1:30` (go to 1:30) · `h` = hours")
        how, value = parsed
        to, length = await player.seek(t.chat_id, **({"to": value} if how == "to" else {"delta": value}))
        arrow = "⏪" if how == "delta" and value < 0 else "⏩"
        await say(m, f"{arrow} **Jumped to** `{fmt_time(to)}` / `{fmt_time(length)}`{t.where}")

    @command
    async def loop(_, m):
        t = await target(app, m)
        arg = "".join(t.args).strip().lower()
        choice = {"on": True, "1": True, "yes": True, "off": False, "0": False, "no": False}.get(arg) if arg else None
        if arg and choice is None:
            raise UserError(f"__Use__ {tag('loop')} __to switch it on / off, or__ {tag('loop')} `on` / `off`")
        enabled = await player.set_loop(t.chat_id, choice, t.user)
        await say(m, f"🔁 **Repeating the current media**{t.where} until you send {tag('loop')} again." if enabled
                  else f"➡️ **Repeat is off**{t.where}, the queue continues after this media.")

    @command
    async def vol(_, m):
        t = await target(app, m, bare="never")
        arg = "".join(t.args).strip().rstrip("%")
        state = app.store.get(t.chat_id)
        if not arg:
            return await say(m, f"🔊 **Volume**{t.where}: `{state.volume}` (1-200, 100 = normal)\n\n{tag('vol')} `<1-200>` to change it")
        if not arg.isdigit() or not 1 <= int(arg) <= 200:
            raise UserError(f"__The volume must be a whole number from 1 to 200 (100 = normal):__ {tag('vol')} `80`")
        applied = await player.set_volume(t.chat_id, int(arg), t.user)
        await say(m, f"🔊 **Volume set to** `{arg}`{t.where}" + ("" if applied else " (applied when something plays)"))

    @command
    async def delete(_, m):
        private_here = not m.command[1:] and m.chat.type.name == "PRIVATE"
        if private_here:      # in private chat without a group: the bot's messages of this chat
            await require_any(app, m)
            chat_id = m.chat.id
        else:
            t = await target(app, m, Role.SUDO if not m.chat.type.name == "PRIVATE" else Role.GROUP_OWNER)
            chat_id = t.chat_id
        reply = m.reply_to_message
        if reply and reply.chat.id == chat_id:
            if not (reply.from_user and reply.from_user.is_self):
                raise UserError("**I can only delete my own messages.**")
            ids = [reply.id]
        else:
            ids = list(app.sent.ids.get(chat_id, []))
        ids = [i for i in ids if not (m.chat.id == chat_id and i == m.id)]
        if not ids:
            raise UserError("**I have no messages to delete there.**")
        for start in range(0, len(ids), 100):
            try:
                await client.delete_messages(chat_id, ids[start:start + 100])
            except Exception:
                pass
        app.sent.forget(chat_id, ids)
        app.cards.forget(chat_id, ids)
        try:
            await m.delete()
        except Exception:
            pass

    for key, handler in (("play", play), ("stream", stream), ("lyrics", lyrics), ("pause", pause), ("resume", resume),
                         ("next", next_), ("end", end), ("queue", queue), ("jump", jump), ("loop", loop), ("vol", vol),
                         ("delete", delete)):
        client.add_handler(MessageHandler(handler, cmd(key)))
