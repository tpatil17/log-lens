# Turnkey GIF recording for the README, via charmbracelet/vhs.
#   brew install vhs         (or: go install github.com/charmbracelet/vhs@latest)
#   vhs examples/demo.tape   ->  writes examples/demo.gif
#
# The second command (--explain) needs OPENAI_API_KEY set in the recording shell;
# delete that block if you want a key-free GIF.

Output examples/demo.gif

Set FontSize 18
Set Width 1120
Set Height 680
Set Padding 20
Set Theme "Dracula"

Type "# A deploy just went out. What changed in the logs?"
Enter
Sleep 1500ms

Type "loglens diff examples/before.log examples/after.log"
Sleep 500ms
Enter
Sleep 3500ms

Type "# Now explain it in plain English (local logs stay local — only a tiny digest is sent)"
Enter
Sleep 1500ms

Type "loglens diff examples/before.log examples/after.log --explain"
Sleep 500ms
Enter
Sleep 6s
