from commandmapper import tag, mode_label as mode

START_TEXT = f"👋🏻 **Video Player is alive!** ✨\n\nI play live links, radios, YouTube videos, songs by name and Telegram audio / video files in the voice chats of your groups. Send {tag('help')} to see the commands."
COMMANDS_LINE = (
    f"🕹 {tag('play')} `<song name or link>` · {tag('play')} `{mode('video')} <name or link>` · reply to audio/video with {tag('play')} · "
    f"{tag('stream')} (force video) · {tag('download')} `<name or link>` · {tag('pause')} · {tag('resume')} · {tag('end')} · {tag('help')}"
)
HELP_TEXT = f"""
🛠-- **Setting Up**:--

\u2022 Start a voice chat in the group!
\u2022 This account must be a member of the group (admin rights are needed if it should start the voice chat itself)!
\u2022 Commands work with `/`, `!` or `.` and only from this account and the SUDO_USERS!

⚔️-- **Available Commands**:--

\u2022 {tag('play')} `<song name>` - Search the song on YouTube and play it as audio
\u2022 {tag('play')} `{mode('video')} <name or link>` - Search or open it and play it as video
\u2022 {tag('play')} `<link>` - Play a YouTube / live / direct link, audio or video is detected automatically
\u2022 reply to an audio or video file with {tag('play')} - Play that file
\u2022 {tag('play')} `{mode('audio')} <name or link>` - Force audio only
\u2022 {tag('stream')} - Same as {tag('play')} `{mode('video')}`
\u2022 {tag('download')} `<song name or link>` - Send the song as an audio file in chat (`{mode('video')}` before the name sends the video)
\u2022 {tag('pause')} - Pause current stream
\u2022 {tag('resume')} - Resume paused stream
\u2022 {tag('end')} - End stream & leave VC
\u2022 {tag('restart')} - Restart the app
\u2022 {tag('about')} - About this app
"""
ABOUT_TEXT = "💡-- **Information**:-- \n\nThis app plays audio and video in Telegram group voice chats from a normal user account, using pytgcalls (group calls) and Pyrogram (MTProto), with yt-dlp for YouTube. \n\n**Licensed under GNU AGPL 3.0!**"
