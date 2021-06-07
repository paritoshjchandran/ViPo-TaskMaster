# ViPo - BOTC TaskMaster

### Features:
* [ ] Help text.
* [x] Silence everyone in 'Town Square' except ST.
* [x] Unmute everyone ST muted.
* [x] Mute Player for reason | Let player unmute.
* [x] Pull everyone from channels starting with /\` and ending with \`\\.
* [x] Day timer with grace period. Pulls everyone back after timer.
* [ ] Game webapp link. (ST and upload and BOT will show on demand).
* [x] Alive/Dead indicator (+all player nicknames).
* [x] Color indicator on Town Square.
* [ ] Check sanity before renaming channels and players (incl. rename mentions)
* [ ] Music in Town Square.
* [ ] Sounds for events.
* [ ] Buddhist timer player mute.
* [ ] Private cottages for night.
* [ ] Pull from private cottages.
* [ ] Destroy private cottages.

### Requests:
* [ ] Audio notification for grace period
* [ ] Incorporate order of players
* [ ] Follow/Record ST


### Stuff to ask bra1n
* [ ] Inform of sending characters to spectators(BOT) with empty role.
* [ ] 
* [ ] 

### Commands:
```
Prefix = !TM- (not case-sensitive)
```
```
Silence, Silencio
Unmute
Pull
Talk, Day, Dawn (args=TalkTimer GracePeriod)
Sleep, Nightfall  # Pending
WakeUp, DayBreak  # Pending
DestroyCottages  # Pending
```

### Story Mode
* Start
* Handle player nicknames
* Voice Channel names (Town Square-Red/White/Green/Yellow)
* Generate and send message
* Seating order

### Time Commands

* sleep
* wake 
* reg public timer
* noms | pause timer when nom is made | resume nom timer | at END ask ST to confirm execution of the day