from commandmapper import tag, alt, mode_alt, mode_label as mode

START_TEXT = f"👋🏻 **Video Player is alive!** ✨\n\nI play live links, radios, YouTube videos, songs by name and Telegram audio / video files in the voice chats of your groups. Send {tag('help')} to see the commands."
COMMANDS_LINE = (
    f"🕹 {tag('play')} `<song name or link>` · {tag('play')} `{mode('video')} <name or link>` · reply to audio/video with {tag('play')} · "
    f"{tag('stream')} (force video) · {tag('download')} `<name or link>` · {tag('pause')} · {tag('resume')} · {tag('next')} · {tag('queue')} · {tag('jump')} `<30s | -10 | +2m>` · {tag('lyrics')} · {tag('loop')} · {tag('vol')} `<1-200>` · {tag('delete')} · {tag('end')} · {tag('help')}"
)
HELP_TEXT = f"""
🛠-- **Setting Up**:--

\u2022 Start a voice chat in the group!
\u2022 This account must be a member of the group (admin rights are needed if it should start the voice chat itself)!
\u2022 Commands work with `/`, `!` or `.` and only from this account and the SUDO_USERS!

⚔️-- **Available Commands**:--

\u2022 {tag('play')}{alt('play')} `<song name>` - Search the song on YouTube and play it as audio
\u2022 {tag('play')}{alt('play')} `{mode('video')} <name or link>` - Search or open it and play it as video
\u2022 {tag('play')}{alt('play')} `<link>` - Play a YouTube / live / direct link, audio or video is detected automatically
\u2022 reply to an audio or video file with {tag('play')}{alt('play')} - Play that file
\u2022 {tag('play')}{alt('play')} `{mode('audio')} <name or link>` - Force audio only
\u2022 {tag('stream')}{alt('stream')} - Same as {tag('play')} `{mode('video')}`
\u2022 {tag('download')}{alt('download')} `<song name or link>` - Send the song as an audio file in chat (`{mode('video')}` before the name sends the video)
\u2022 {tag('pause')}{alt('pause')} - Pause current stream
\u2022 {tag('resume')}{alt('resume')} - Resume paused stream
\u2022 {tag('next')}{alt('next')} - Skip to the next queued item
\u2022 {tag('queue')}{alt('queue')} - Show what is playing and what is queued
\u2022 {tag('jump')}{alt('jump')} `<time>` - Move in the current media: `30`, `+30s` or `+5m` go ahead, `-10`, `-40s` or `-2m` go back. Units: `s` seconds (default), `m` minutes, `h` hours\n\u2022 {tag('lyrics')}{alt('lyrics')} `<song name or link>` - Play the song as a video that shows its synced lyrics (Persian and other right-to-left text works); without a name it turns the song that plays now into a lyrics video. Plays normally when no synced lyrics are found\n\u2022 {tag('loop')}{alt('loop')} - Repeat the current media until you turn it off ({tag('loop')} again, or `off`); it also ends with {tag('next')} / a new stream\n\u2022 {tag('vol')}{alt('vol')} `<1-200>` - Set the bot's volume in the voice chat (100 = normal), without a number it shows the current volume\n\u2022 {tag('delete')}{alt('delete')} - Delete all messages the bot sent in this chat, or only one when you reply to it with this command\n\u2022 While something plays, {tag('play')} / {tag('stream')} add the new item to the queue instead of replacing it
\u2022 {tag('end')}{alt('end')} - End stream, clear the queue & leave VC
\u2022 {tag('restart')}{alt('restart')} - Restart the app
\u2022 {tag('list')}{alt('list')} - Owners only, in private chat: numbered list of the groups this account has joined
\u2022 {tag('play')} `<number>` - Owners only, in private chat: reply to a link / audio / video you sent me with it (or add the link after the number) to play it in the group with that number of {tag('list')}; it joins the queue when that group already plays something
\u2022 {tag('join')}{alt('join')} `<invite link or @username>` - Owners only: join that group
\u2022 {tag('leave')}{alt('leave')} `<number>` - Owners only: leave the group with that number of {tag('list')}; inside a group without a number it leaves that group
\u2022 {tag('sudolist')}{alt('sudolist')} - Owners only, in groups and private chat: numbered list of the SUDO users with their names
\u2022 {tag('addsudo')}{alt('addsudo')} `<id or @username>` - Owners only: add a SUDO user (or reply to the person's message)
\u2022 {tag('delsudo')}{alt('delsudo')} `<number, id or @username>` - Owners only: remove a SUDO user (number of {tag('sudolist')}, or reply to the person's message)
\u2022 {tag('id')}{alt('id')} - Open to everyone, private chat only: replies with your Telegram number (ID)\n\u2022 {tag('about')}{alt('about')} - About this app
\u2022 {tag('help')}{alt('help')} / {tag('start')}{alt('start')} - This list / short intro
\u2022 Words after {tag('play')}: `{mode('video')}`{mode_alt('video')} · `{mode('audio')}`{mode_alt('audio')}
"""
ABOUT_TEXT = "💡-- **Information**:-- \n\nThis app plays audio and video in Telegram group voice chats from a normal user account."
