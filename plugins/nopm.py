"""Optional text auto-reply to private messages of people without a role (REPLY_MESSAGE in .env)."""

from pyrogram import filters
from pyrogram.handlers import MessageHandler


def register(app) -> None:
    text = app.settings.reply_message
    if not text:
        return
    last: dict[int, int] = {}
    prefixes = tuple(app.settings.prefixes)

    async def nopm(client, m):
        if app.acl.has_any_role(m.from_user.id if m.from_user else None):
            return                      # people with a role talk to the bot, they get no auto-reply
        if (m.text or "").startswith(prefixes):
            return                      # commands (/id is open to everyone)
        try:
            reply = await m.reply_text(text, quote=False)
            old = last.get(m.chat.id)
            if old:
                await client.delete_messages(m.chat.id, old)
            last[m.chat.id] = reply.id
        except Exception:
            pass

    app.client.add_handler(MessageHandler(
        nopm, filters.private & filters.incoming & ~filters.bot & ~filters.service & ~filters.me & ~filters.chat([777000, 454000])), group=1)
