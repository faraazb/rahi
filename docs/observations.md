# Observations: official sources vs Yatri

A running log of where the official timetables and Yatri's bundled database disagree, and
of mistakes in the official PDFs themselves. Each entry says how it was checked:

- **seen**: checked by eye on a rendered PDF page.
- **parsed**: taken from our parser's output and matches the PDF text, but not looked at by eye.

Yatri's database is used as a local cross-check. Nothing from it goes into published data. Local
builds can add its platform numbers as a separate `platform` table (`mise run platforms`), which the
release step refuses to publish.

---

## WR: PTT-79, w.e.f. 01.09.2026 (checked 2026-11-01 to 2026-11-04)

**Source:** `oldwr.indianrailways.gov.in`, 5 PDFs in `data/raw/wr/2026-09-01/`
(Last-Modified 31 Aug 2026).

**Compared with:** Yatri's `yatri.db`, line 2 (Western), suburban-numbered trains only. Its 89
express (EXP) and 3 ETY rows are left out of the comparison.

### Summary

| | |
|---|---|
| Trips parsed | 1,406 |
| Trains in both | 1,294 |
| Identical (same stations, same times) | 1,236 (95.5%) |
| Stop times exact, at stations both have | 20,469 / 20,500 (99.8%) |
| Fast/slow agrees | 1,289 / 1,294 |
| Car count agrees | 1,291 / 1,294 |

Every difference below was traced to the PDF or to Yatri. None comes from the parser.

### 1. Terminus times missing in the PDF, filled in by Yatri

At 32 stops on 31 trains, the PDF leaves the time blank at the start or end of the run, and
Yatri has a time there. That time is not printed anywhere in the PDF. We keep what the PDF
says and do not make up a time.

**DN trains, terminus named in the header but its cell blank (7).** We keep the destination
and set `dest_time_missing = 1`.

| Train | Header terminus | Yatri's time |
|---|---|---|
| 90165 | ADH | 08:29 (seen: the Andheri cell is blank) |
| 90343 | ADH | 11:30 |
| 90653 | ADH | 17:27 |
| 90675 | ADH | 17:52 |
| 90711 | ADH | 18:30 |
| 90799 | ADH | 19:55 |
| 90885 | BVI | 21:36 |

**UP trains, where the PDF simply stops timing the train (24).** On the UP sheet the header
gives the origin, so the PDF names no destination either.

- 92116: seen. The 15-car train is timed from VR 12:09 to Dahisar 12:39, then the column is blank. Yatri adds BVI 12:45.
- 92118: Yatri adds a time at both ends, BSR 12:20 and DDR 13:16.
- The rest (parsed), Yatri's extra stop in brackets:

  | | | | |
  |---|---|---|---|
  | 90486 (DDR 13:55) | 90732 (BVI 18:00) | 90852 (DDR 20:35) | 90858 (BVI 20:16) |
  | 90966 (BVI 22:32) | 91024 (BVI 00:32) | 92070 (DDR 10:10) | 92076 (DDR 10:24) |
  | 92114 (ADH 13:03) | 92174 (BVI 17:36) | 92194 (BVI 18:46) | 92202 (BVI 19:17) |
  | 92212 (BVI 20:10) | 92214 (BVI 20:34) | 92216 (ADH 21:18) | 92218 (BVI 21:05) |
  | 92226 (BVI 21:55) | 92232 (BVI 22:21) | 94100 (BVI 17:26) | 94116 (DDR 19:31) |
  | 94144 (BVI 22:46) | 94148 (BVI 23:11) | | |

**Open question:** these UP 15-car and short-run trains may really run on to the station
Yatri gives. Yatri may have the information from somewhere else, or may have guessed it. It
needs a second official source, such as NTES or a station display.

### 2. Yatri wrong where the PDF is clear

| Train | PDF | Yatri | Check |
|---|---|---|---|
| 91039 DN | Prabhadevi printed "12:28" between 00:25 and 00:30 (a typo for 00:28) | 12:28 (copied the typo) | seen; we correct it and log `time-corrected-12h` |
| 90796 UP | Prabhadevi 19:54 | stop missing, so it calls the train fast | seen; it stops at every station BVI to CCG |
| 94123 DN | Vile Parle "20;02" (semicolon typo) | stop missing, so it calls the train fast | parsed |
| 91012 UP | a stray "``" mark where the Goregaon time should be | GMN 00:16 (made up) | seen |
| 93006 UP | DRD to VR, stops everywhere | fast | parsed; same stops in both |
| 93035 DN | timed from DDR and skips the stations between DDR and BVI | slow | parsed; same stops in both |
| 94111 DN | Borivali 18:52 on both `dn.pdf` and `ac_dn.pdf` | 18:54 | parsed from both sheets |
| 90690 UP, 90730 UP, 91009 DN | header "12 CAR" | 15 coaches | parsed from the header text |

### 3. Dahanu section: different times at the far stations

20 Dahanu trains differ at one or two of KLV, VGN, PLG or BOR, by 5 to 14 minutes (23 station
times). Our times
match the Dahanu sheet (`drd.pdf`). Seen on the rendered sheet: 93001 KLV 05:16, 93002 VGN
04:50, 93004 PLG 06:27, 93005 KLV 06:40, 93021 BOR 12:54, 93031 KLV 16:55, 93202 VGN 07:34.

| Train | Station | PDF | Yatri |
|---|---|---|---|
| 93001 DN | KLV | 05:16 | 05:23 |
| 93002 UP | VGN | 04:50 | 04:56 |
| 93004 UP | PLG | 06:27 | 06:37 |
| 93005 DN | KLV | 06:40 | 06:47 |
| 93005 DN | VGN | 07:17 | 07:22 |
| 93007 DN | KLV | 07:29 | 07:35 |
| 93012 UP | KLV | 10:20 | 10:25 |
| 93013 DN | KLV | 09:56 | 10:02 |
| 93018 UP | VGN | 11:45 | 11:51 |
| 93020 UP | VGN | 12:40 | 12:45 |
| 93021 DN | KLV | 12:26 | 12:31 |
| 93021 DN | BOR | 12:54 | 13:07 |
| 93023 DN | BOR | 13:19 | 13:24 |
| 93026 UP | VGN | 14:17 | 14:28 |
| 93028 UP | PLG | 15:56 | 16:06 |
| 93029 DN | BOR | 16:32 | 16:43 |
| 93031 DN | KLV | 16:55 | 17:09 |
| 93037 DN | KLV | 20:55 | 21:09 |
| 93038 UP | VGN | 20:02 | 20:07 |
| 93040 UP | VGN | 21:02 | 21:08 |
| 93041 DN | KLV | 22:06 | 22:12 |
| 93041 DN | BOR | 22:33 | 22:38 |
| 93202 UP | VGN | 07:34 | 07:46 |

Yatri may be using arrival times, or a different revision, for the Dahanu section; the PDF
gives one time per station.

**The PDF disagrees with itself (1 minute).** The main sheet and the Dahanu sheet differ by a
minute at CYR or GTR on 93005, 93007 and 93009, and at BYR on 93022. We keep the main sheet's
time and log `merge-minute-difference`. Yatri uses the Dahanu sheet's time.

### 4. Service days: Yatri says "not on Sunday", the PDF says nothing

Among the 1,238 trains whose times match, 53 have different running days:

| Ours (from the PDF) | Yatri | Trains |
|---|---|---|
| daily, no day note found | Y (not on Sunday) | 35 |
| daily, no day note found | X (not on Sunday or holidays) | 12 |
| daily, note reads "SUN & HOLIDAY" (see §5) | X | 3: 90047, 90088, 90309 |
| not on Sunday | daily | 2: 90333, 91023 |
| Sunday only, note reads "SUN ONLY" | Y (not on Sunday) | 1: 90264 (seen) |

90017 was seen: there is no note anywhere in its column. The 47 trains with no note are:

90008, 90017, 90035, 90045, 90084, 90086, 90097, 90112, 90145, 90163, 90236, 90254, 90289,
90301, 90366, 90398, 90405, 90453, 90500, 90503, 90508, 90517, 90558, 90566, 90595, 90610,
90627, 90650, 90692, 90708, 90715, 90740, 90759, 90775, 90828, 90836, 90848, 90881, 90909,
90918, 90921, 90929, 90946, 90964, 90979, 90987, 90996.

**Open question:** Yatri may get these days from another source, such as WR notices or the
Sunday timetable. Running days are what riders depend on most, so this needs a second
official source before launch.

### 5. Notes that look cut short in the PDF

Our parser flags these as `ambiguous day note` and keeps the literal reading. It does not
guess.

| Train | Printed | Probably meant | Stored as |
|---|---|---|---|
| 90047 DN | SUN & HOLIDAY | NOT ON SUN & HOLIDAY | daily |
| 90088 UP | SUN & HOLIDAY | NOT ON SUN & HOLIDAY | daily |
| 90309 DN | SUN & HOLIDAY | NOT ON SUN & HOLIDAY | daily |
| 94058 UP | ON SAT & SUN / Air Condition | ON SAT & SUN NON AC | AC every day |
| 94120 UP | ON SAT & SUN / Air Condition | ON SAT & SUN NON AC | AC every day |
| 94148 UP | ON SAT & SUN / Air Condition | ON SAT & SUN NON AC | AC every day |

90264 UP prints just "SUN ONLY" (seen). Every other train with this kind of note reads "NOT ON
/ SUN / ONLY", so the "NOT ON" line was probably lost. It is stored as Sunday only, which
contradicts Yatri. **This one needs a decision.**

### 6. Other mistakes and quirks in the PDF (the parser handles them)

- Station typos: "CHERNI ROAD" and "MERINE LINE" on the Dahanu sheet, and "CSTM" for CSMT in Harbour columns. These are added as aliases.
- 93033 DN: the Dahanu sheet header says VR-DRD, but the main sheet times it from Dadar 17:22 (seen). We use the times and log `terminal-mismatch`.
- Two Dahanu UP headers are printed touching ("DRD-CCGDRD-CCG") and come out as one word.
- A stray "2" is printed above the Bandra row of 90400 UP (seen). It is kept as a note and has no effect.
- "P*" cells mean a pass with a footnote, e.g. "*92115 Will Not Halt at Bandra & Borivali".
- Harbour trains (header `C.R.GMN`, `C.R.CSMT`, `C.R.PNVL`, or `WGN n` / `WBO1`) print their CSMT or Panvel time as a note in an unrelated row ("EX / CSMT / 04:28" in the Prabhadevi row).

### 7. Train numbers only in Yatri

These numbers appear nowhere in the PTT-79 PDFs: 69174 (a 20-coach MEMU, which is not part of
the suburban timetable), 90036, 90040, 90111, 90122, 90124, 90126, 90659, 92179. They are
probably stale rows for trains renumbered or withdrawn in PTT-79.

### 8. Trains only we have

112 numbers. Most are Central Railway Harbour trains printed on the WR sheet (98xxx, 91392 to
91396, 91491); Yatri files these under the Harbour line. Since 2026-11-07 the combined build
(`mise run build`) keeps the Harbour sheet's copy of each and drops WR's
(`cross-railway-copy-dropped`). With that, WR has no trains Yatri lacks. All 112 WR copies agree with
the Harbour sheet except 91491 (see CR §6) and 91393, which has no Andheri time on the WR sheet.

---

## CR: sheets downloaded 2026-11-01 (checked 2026-11-07)

**Source:** `oldcr.indianrailways.gov.in`, 12 PDFs in `data/raw/cr/2026-11-01/` (URLs and
Last-Modified dates in `SOURCES.txt`). The parser is `pipeline/src/mumbailocal/sources/cr.py`.

| File | Line | Edition |
|---|---|---|
| `main_dn.pdf`, `main_up.pdf` | CR | "ML'24", Last-Modified 07.10.2024 |
| `main_15car.pdf` | CR | w.e.f. 15.08.2026 |
| `ac.pdf` | CR | w.e.f. 16.04.2025 |
| `hb_dn.pdf`, `hb_up.pdf`, `hb_ac.pdf` | HR | w.e.f. 01.05.2026 |
| `thb.pdf` | THR | w.e.f. 13.01.2024 |
| `port.pdf` | UR | w.e.f. 15.12.2025 |
| `lnl_pune.pdf`, `pune_lnl.pdf` | PUNE | no date printed |

**Compared with:** Yatri's `yatri.db` (schedule rows updated up to 2026-09-02): line 1 (Central),
3 (Harbour), 4 (Trans Harbour), 5 (Uran) and 8 (Pune-Lonavla).

### Summary

| | CR | HR | THR | UR | PUNE |
|---|---|---|---|---|---|
| Trips parsed | 895 | 614 | 262 | 50 | 42 |
| Trains in Yatri | 892 | 614 | 262 | 50 | 42 |
| Trains in both | 892 | 614 | 262 | 50 | 40 |
| Identical (same stations, same times) | 883 (99.0%) | 610 (99.3%) | 262 (100%) | 50 (100%) | 39 |
| Stop times exact, at stations both have | 16,833 / 16,845 | 11,919 / 11,929 | 2,802 / 2,802 | 474 / 474 | 617 / 620 |

The Main line sheets are the 2024 edition, yet 99% of their trains match Yatri's 2026 data, so
the timetable has hardly changed since. Every time difference below was checked against the PDF
cells: the parser reads what is printed. The running days (§4) and the AC flags (§5) are where
the sources really disagree.

### 1. Stations the PDF leaves blank, where Yatri has a time

The cell is empty in the PDF, so we treat the train as not stopping there (and call it fast).
Yatri has a time at that station and calls the train slow. All six trains run late at night.

| Train | Blank station | Check |
|---|---|---|
| 96649 DN (CSMT 22:50) | Diva, between Mumbra 23:56 and Kopar 00:05 | seen, `main_dn.pdf` p18 |
| 96651 DN (CSMT 23:16) | Bhandup | parsed |
| 97441 DN (CSMT 23:55) | Sandhurst Road | parsed |
| 97436 UP (Thane 23:40) | Ghatkopar | parsed |
| 97182 UP (Kalyan 23:47) | Kopar | parsed |
| 98785 DN (CSMT 23:26) | Khar Road | parsed |

**Open question:** these may be real night-time skips or gaps in the PDF. Yatri may have the
times from somewhere else.

### 2. Yatri stops a train where the PDF prints a pass

- 95230 UP (Badlapur 16:47, 15-car): the PDF prints "…" (passes without stopping) at Diva and
  Mulund, on both the Main sheet and the 15-car sheet. Yatri has it stopping at both. Parsed.

### 3. Different times

| Train | PDF | Yatri | Check |
|---|---|---|---|
| 95134 UP | CSMT 19:34 (15-car sheet, 2026) | 19:28 (same as the 2024 Main sheet) | parsed |
| 95129 DN | Kalyan 19:23 (15-car sheet) | 19:22 | parsed |
| 98194 UP | Nerul 19:39 | 19:36 | parsed |
| 98803 DN | Mahim 01:00, Bandra 01:04 | 01:01, 01:05 | parsed |
| 96341 DN | Main sheet 2024: slow 12-car, CSMT 23:08 .. Ambernath 00:50, 29 stops | fast 15-car, 11 stops, arrives up to 20 min earlier | parsed. Not on the 15-car sheet, so the PDFs have no current version |
| 99904 UP (Pune) | Dehu Road 09:26, Begdewadi 09:30, Ghorawadi 09:33 | one minute later at each | parsed |
| 99819 DN (Pune) | Lonavala 18:10 | Yatri's 01567, the same run 2 min earlier | parsed |
| 99832 UP (Pune) | Shivajinagar 21:10 | Yatri's 01580, the same run 5 min earlier | parsed |

### 4. Running days

The sheets mark days with letters above the first station and never explain most of them. `X`
is defined only on the Harbour AC sheet ("will not run on Sundays/Nominated Holidays"). We read
it that way on every sheet. `XX` and a bare `#` are not defined anywhere, so we keep the train
daily and report the mark (`unrecognized_notes`).

- **Yatri says X ("not on Sunday/holidays"), the PDF has no mark: 82 CR trains.** Seen for 97001
  (`main_dn.pdf` p1: X only under 97003 and 97005). The trains: 95601 95606 95708 95714
  95722 95735 95740 95803 95905 95910 95915 97001 97017 97025 97036 97045 97054 97078 97080 97089
  97098 97102 97105 97112 97119 97125 97128 97131 97135 97136 97138 97159 97161 97201 97205 97206
  97208 97213 97216 97219 97222 97231 97234 97238 97245 97246 97248 97250 97257 97258 97264 97315
  97317 97326 97329 97336 97337 97339 97348 97350 97351 97365 97373 97380 97386 97387 97394 97396
  97407 97409 97412 97421 97423 97425 97426 97437 97605 97606 97621 97623 97629 97645. On Harbour:
  98089 and 98520 (X), 98732 (Y, "not on Sunday").
- **The PDF says X, Yatri says the train runs on Sunday as an ordinary rake ("#" or "###"): 14
  CR AC trains.** These are 97013, 97026, 97359, 97366, 97378, 97383, 97402, 97403 and 97424 (###), and
  97369, 97389, 97408, 97618 and 97630 (#). `ac.pdf` p1 prints "AC # / X" for 97013 (seen).
- **The PDF says X, Yatri says Y (Sundays only, holidays not mentioned):** 98703, 98710, 98759,
  98766 (Harbour).
- **The PDF says X, Yatri has no exception: 16 Trans-Harbour trains.** 99008, 99019, 99048, 99053,
  99065, 99068, 99205, 99206, 99219, 99220, 99249, 99250, 99255, 99256, 99417, 99422. The THB
  sheet's legend explains only `$`.
- **XX:** 95801 (15-car sheet), stored daily. Yatri reads it as "not on Saturday/Sunday/holidays".

**Needs a decision:** the 82 extra X trains in Yatri are the largest gap. They may come from a
CR notice or the holiday list. As on WR, riders depend on these days, so this needs a second
official source before launch. It also needs an official legend for `XX` and `#`.

### 5. AC flags

- **Yatri marks 12 trains AC; no PDF does:** 96603, 96612, 97157, 97164, 97389, 97408, 97433, 97501,
  97502, 97615, 97618, 97630. The AC sheet dates from 16.04.2025 and Yatri from 2026, so these are
  probably newer AC services. Neither the Main nor the AC sheet marks them.
- The Harbour AC sheet's footnote says "All of the above services running on Sunday/ Nominated
  Holidays will run with Non AC rake". The schema can only say "AC Monday to Friday"
  (`ac_weekdays_only`), which would wrongly drop Saturday, so the footnote is kept as a train note
  only. **Needs a schema decision** (an `ac_days` mask).
- `$` on the THB sheet means "TNA end 3 Coaches reserved for Ladies only". Yatri has the same
  property. We keep it as a note.

### 6. Official sheets that disagree with each other

- **91491 (CSMT -> Borivali), WR sheet (PTT-79, 01.09.2026) vs Harbour sheet (01.05.2026).** They
  agree as far as Vile Parle. After that WR has Andheri 21:31, Jogeshwari 21:35, Ram Mandir 21:38,
  Goregaon 21:40, Malad 21:44, Kandivli 21:47, Borivali 21:53. The Harbour sheet has 21:27, 21:31,
  21:34, 21:38, then Borivali 21:50 (seen, `hb_dn.pdf` p16, "BVI" printed in the Kurla row).
  Yatri follows WR. The build keeps the Harbour copy, which is the only one timed from CSMT, and
  reports the conflict. **Needs a decision** whether WR's newer times should win north of Bandra.
- **15-car sheet (15.08.2026) vs Main sheets (2024).** The newer sheet wins (`sheet-superseded`),
  and Yatri agrees with it every time.
  - 96312 UP is retimed from Kalyan on, by up to 27 minutes, and is now fast.
  - 95134 arrives at CSMT 6 minutes later than on the Main sheet.
  - 95717 is 1 minute later at CSMT and Kalyan.
  - 95002, 95003 and 95344 start or end at Dadar on the 15-car sheet but at CSMT on the Main sheet.
- **AC sheet vs Main sheets.** The Main sheets print 14 AC services without the "AC" mark. The
  build takes the flag from the AC sheet. 97041's Kalyan time appears only on the AC sheet.
- **Only on the 15-car sheet:** 95017, 95335 and 95337 DN. They appear neither in Yatri nor on the
  Main sheet, so they are probably new 15-car services from August 2026.

### 7. Yatri wrong where the PDF is clear

| Train | PDF | Yatri | Check |
|---|---|---|---|
| 96003 DN | Karjat 8:00 to Khopoli 8:25, every station | fast | parsed; same stops in both |
| 96324 UP, 97203 DN | stops at every station on its run | fast | parsed; same stops in both |
| 98901 to 98918 | Panvel <-> Goregaon via Vadala, odd numbers towards Goregaon | 98901 Panvel -> Goregaon filed as "Up" | parsed; we use the number's parity |
| 95737 DN | no "15 C" mark | 15 coaches | parsed |

Yatri numbers the 40 Pune locals 01551 to 01592, while the sheets print 99801 to 99834 and 99901
to 99908. The comparison pairs them by direction, first station and departure time.

### 8. Layout quirks the parser handles

- **Branches stacked in the rows.** The Main sheets list CSMT to Kalyan, then the Karjat/Khopoli
  branch, then the Kasara branch. The Harbour sheets list CSMT to Vadala, then Goregaon, then Panvel.
  Stops are ordered along the track graph in `data/stations/<line>.csv` (the `prev` column).
- **Panvel <-> Goregaon trains (989xx) are printed in two halves**, one in the UP table up to Vadala
  and one in the DN table from Vadala, under the same number. The parser joins them into one trip
  (`joined-across-tables`, 18 trains).
- **Invisible text.** White "00:00" and "0" are printed in empty cells and rows, and pdfplumber
  reads them like any other text. The parser skips white text on CR sheets (`drop_white`).
- **Off-sheet terminals in the cells.** "TNA" in the CSMT row (a Trans-Harbour train shown on the
  Harbour sheet), "BVI" above Borivali's time, "DR" in the CSMT row (15-car trains from Dadar).
- **Rake notes.** "R/O / VVD 2 / 04:56" above 98009's first time names the incoming rake working
  and its time. It is not a Reay Road departure (seen, `hb_ac.pdf` p1; 98119 and 98181 are the
  same).
- The Pune sheets print each time between the "A:" and "D:" lines, with "X" for "does not run
  here" and "Thr..." for a pass. "05.20" uses a dot.
- Station spellings: "DLY" (Dolavli) on the 15-car UP page, "Ramnagar" for Ram Mandir, "DIGH" for
  Digha Gaon, "SNPD" for Sanpada, "Diwa", "Umbermalli".
- The Port line has two origins, Nerul and Belapur, which join at Targhar.

---

## NTES: Vasai–Diva–Panvel MEMUs and Neral–Matheran, saved 2026-11-07 (checked 2026-11-08)

No suburban PDF lists these trains. NTES (enquiry.indianrail.gov.in/mntes) publishes one schedule
page per train. The pages are kept unchanged in `data/raw/ntes/2026-11-07/`. The trains were
found in NTES's train list by number: 610xx and 69161–69168 are the MEMUs, 521xx the hill
railway (see `train_list.txt`).

### Summary

| Line | Trains (ours / Yatri) | Identical | Stop times exact | Notes |
|---|---|---|---|---|
| DVP | 31 / 30 | 17 (+2 within a minute) | 298/359 (83.0%) | 61001 only ours; 11 marked daily by Yatri |
| NM | 16 / 16 (+4 Yatri specials) | 12 | 30/44 (68.2%) | Yatri last edited Mar 2023 |

The parser takes every time straight from the page, so each difference below is NTES against
Yatri. Where they disagree, NTES is the official source. Checked by **parsed**, against the saved page.

### 1. Stations

- NTES codes Kopar's upper level `KORU` and Neral's narrow-gauge station `NRLN`. Both are stored
  as the Kopar (`KOPR`) and Neral (`NRL`) interchanges, so a rider sees one station at each.
- Yatri spells Nilaje "Nilje" (alias added). It also uses its own codes DTCC (Dativali), KLMC
  (Kalamboli) and SMTN (Somatne). NTES calls Kalamboli "Kalamboli Goods" and Dativali "Dativali Cabin".
- Panvel ↔ Vasai trains leave the Diva line at Dativali and join the Vasai line at Kopar. They do
  not call at Diva, so the station graph has a loop (Diva–Kopar–Dativali).

### 2. Yatri stops trains where NTES has no halt

- 69161, 69165, 69167 (Panvel → Vasai / Dahanu): Yatri has a Kopar stop; NTES lists none (the
  even-numbered return trains do halt there). We store them as running through Kopar, so they
  show as "fast" between Dativali and Bhiwandi Road.
- 69161 also has no Navade Road halt in NTES.
- 61002 Dombivli → Boisar: NTES has a Nallasopara halt; Yatri does not.

### 3. Different times

- 61002: Vasai Road arr 06:45 dep 07:00 in NTES (Yatri 06:40). Every later stop is 6–10 minutes
  later in NTES, e.g. Boisar 08:20 vs 08:10.
- 61003: Vasai Road departure 09:50 (Yatri 09:40).
- 61012 Roha → Diva: starts 15:40 in NTES, 15:55 in Yatri; 10–17 minutes apart all the way.
- 61013, 61015, 61025, 61026, 69164: 1–7 minute differences on the Pen/Roha and Dahanu ends.
- 69161: 5–10 minutes apart between Nallasopara and Vangaon.
- Matheran: 52105 Neral 10:25 in NTES, 14:20 in Yatri (3 h 55 min); 52106 20 minutes earlier in
  NTES; 52159/52160 20 minutes later in NTES. Yatri's Matheran trains were last updated in March 2023.

### 4. Running days

- 12 MEMUs run Monday to Friday only in NTES (61015–61026). Yatri agrees for 61021 and marks the other 11 as daily.
- NTES says nothing about holidays. Those trains are stored as weekday-only, with no holiday flag.

### 5. Trains on one side only

- 61001 Boisar → Vasai Road is in NTES, not in Yatri.
- Yatri's Matheran specials "7-SPL 1" to "7-SPL 4" have no NTES schedule, so we do not include them.

### 6. Direction

- We set direction by number (odd = DN), as on the CR sheets. Yatri does the same for 610xx and
  521xx, but files 69161–69168 the other way (Panvel → Dahanu as up). This line has no single
  "towards Mumbai" end, so the app names each direction after where its trains go.

---

## How to reproduce

```sh
mise run build -- --wr data/raw/wr/2026-09-01 --cr data/raw/cr/2026-11-01 --ntes data/raw/ntes/2026-11-07   # writes pipeline/build/mumbai-local.sqlite
# Yatri DB, for local checking only (never committed): temp.fignore/yatri/yatri.db
mise run compare -- --line WR          # or CR, HR, THR, UR, PUNE, DVP, NM; --details out.tsv lists every train that differs
```
