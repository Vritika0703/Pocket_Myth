# Man-Beater Score site: design direction

The site presents the analysis in this repo in two modes, switched with one toggle in the header.
Both modes use the same page and the same words. Only the presentation changes.

## Game mode (default)

Reading this as: a sports-analytics results page for football fans and hackathon judges, in a
night-game broadcast-graphics style, dial ENERGY 3 / RHYTHM 3 / MOTION 2.

- Palette: turf green `#0c3326`, chalk `#f4f1e8`, one accent: line-to-gain yellow `#ffd23f`.
  Reason: a night broadcast is turf under lights with white chalk, and the yellow first-down line is the
  one mark every viewer reads as "the line to beat".
- Accent rule: yellow appears only where something is measured against a benchmark: the line under the
  headline and the "expected" zero line in every chart. Nothing decorative is yellow.
- Dark by default. Reason: the mode imitates a night-game broadcast; Article mode is the light option.
- Type: Barlow Condensed 800/600 for headlines, names and numbers; Barlow 400/600 for text.
  Reason: broadcast score graphics use condensed heavy type so long names ("Amon-Ra St. Brown") and
  numbers fit narrow bars; Barlow's normal width shares the skeleton and stays readable for paragraphs.
- Uppercase is limited to player names in the "Open but ignored" lower thirds and the header score bug,
  with normal tracking. Reason: that is how broadcast lower thirds set names.
- Texture: 5-yard mowing bands behind the opening section only. Reason: the metric is measured in yards,
  and the bands make the page read as a field without a single icon.
- Section markers: Pregame, Q1 to Q4, OT for the bonus analysis, Postgame, Film room. The header score
  bug shows the current one while scrolling. Reason: the page is read in segments like a broadcast, and
  the bug doubles as a "where am I" indicator on a long page.
- Layout: sections change composition (text beside figure, full-width scoreboard panel, full-width chart,
  lower-third list, two-column fine print). Reason: RHYTHM 3; each block is shaped by its content.
- Motion: the toggle wipe (covers the re-layout when switching modes), the headline line drawing in once,
  and leaderboard marks sliding out from the expected line the first time the table scrolls into view
  (each score is a distance from expected). All of it stops under `prefers-reduced-motion`.

## Article mode

Reading this as: a long-form data-journalism article for coaches, scouts and analysts, in a newsprint
reading style, dial ENERGY 1 / RHYTHM 2 / MOTION 1.

- Palette: paper `#faf7f0`, ink `#1c1a16`, one accent: man-coverage red `#c8102e`.
  Reason: the red is the colour `src/man_beater.py` already uses for man coverage, so the site and the
  repo's charts mean the same thing by it.
- Accent rule: red marks man coverage in the payoff chart and the four "open but ignored" players named
  in the README. Zone coverage and everything else stay ink or grey.
- Type: Newsreader for headline and text; Barlow for chart labels, tables and controls.
  Reason: Newsreader was drawn for long news text on screens; keeping Barlow for labels in both modes
  means axes, tables and the toggle keep the same metrics when the mode changes.
- Layout: one reading column of about 66 characters; figures break out wider. Reason: RHYTHM 2, an
  article read top to bottom, with the charts as the only breaks.
- Motion: hover and focus states only. The toggle wipe belongs to the toggle, not to the mode.

## Shared decisions

- Charts are drawn from the repo's own CSV files at page load, so the site shows whatever the analysis
  last wrote to `output/`. The payoff chart is the exception: its 24 numbers are a small table in the page,
  computed from `output/route_separation.csv` with the bins in `src/man_beater.py`.
- Player position is shown by shape (WR circle, TE square, RB diamond), not colour. Reason: it keeps each
  mode at one accent, and the chart still reads in greyscale and for colour-blind readers.
- No cards except where the content is a list of equal items (the lower thirds). No shadows except the
  sticky header in Game mode, which sits above the content while scrolling.
- Radius: 2px everywhere. Reason: broadcast graphics and newsprint are both square-edged.
- No logo, photos or team names were supplied, so the project name is set as text and nobody is pictured.
- If a CSV fails to load, the block says which file failed, offers a retry, and shows the repo's static
  chart for that finding.
