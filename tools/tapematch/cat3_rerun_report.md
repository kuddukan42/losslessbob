# Cat-3 focused re-run report (Task 2) — 2026-07-02T17:37:47-05:00
# Cat-3 = curator-says-same + verdict different_family + speed-aligned to a wrong 3rd reference.
# Fix: stage ONLY the two folders so they align against each other. Expect most to flip.

  Copying LB-00758: 1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758) …
  Copying LB-05125: 1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125) …
  [cleanup] removed stale tmp dir: tapematch_df740lmw
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.8 GB (2 sources, largest 1:12:16)
=== INGEST / TRIM ===
  1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125): 15 tracks, 1:12:16
  1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758): 14 tracks, 1:01:17

=== TRIM (performance envelope) ===
  1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125): trimmed 0:01:27 head, 0:00:11 tail -> performance 1:10:38
  1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758): trimmed 0:03:15 head, 0:00:24 tail -> performance 0:57:38

  [INCOMPLETE?] — duration well below group median (1:04:08):
    1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758): 0:57:38 (10.1% shorter)

=== ANCHORS (ref=1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125)) ===
  0:03:02, 0:06:41, 0:15:23, 0:21:58, 0:23:37, 0:31:24, 0:38:14, 0:43:15, 0:51:46, 0:53:20, 1:00:04, 1:10:35

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125)->1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758): speed-unknown  speed ratio=1.016800 (+16800 ppm)  [conf=2.1]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-05125  LB-00758
  LB-05125     1.000     0.003
  LB-00758     0.003     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125)  (mean intra-corr 1.000)
  Family 2: 1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-07 Jerusalem, Israel, Sultan's Pool (LB-05125)       2.0kHz      -73.3dB      +0.00016
  1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758)       2.0kHz      -82.2dB      -0.00002
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [INCOMPLETE] 1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758): 0:57:38 vs median 1:04:08 (10.1% shorter) — likely missing material
  [DISTINCT SOURCE] 1987-09-07 Sultan's Pool, Jerusalem, Israel (LB-00758) (+16800 ppm speed offset, best cross-family corr 0.003): near-zero correlation to all other sources — entirely different recording
  1987-09-07  LB-00758/LB-05125: different_family -> different_family  [unchanged]
  Copying LB-00134: 1987-09-15 Dortmund, West Germany (LB-00134) …
  Copying LB-06029: 1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029) …
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.8 GB (2 sources, largest 1:11:40)
=== INGEST / TRIM ===
  1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029): 14 tracks, 1:11:40
  1987-09-15 Dortmund, West Germany (LB-00134): 14 tracks, 1:08:45

=== TRIM (performance envelope) ===
  1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029): trimmed 0:01:20 head, 0:01:03 tail -> performance 1:09:16
  1987-09-15 Dortmund, West Germany (LB-00134): trimmed 0:03:18 head, 0:00:09 tail -> performance 1:05:18

=== ANCHORS (ref=1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029)) ===
  0:02:42, 0:06:37, 0:15:57, 0:19:51, 0:28:13, 0:29:52, 0:39:12, 0:40:43, 0:51:11, 0:54:55, 1:02:04, 1:06:41

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029)->1987-09-15 Dortmund, West Germany (LB-00134): speed-unknown  speed ratio=1.058008 (+58008 ppm)  [conf=4.3]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-06029  LB-00134
  LB-06029     1.000     0.001
  LB-00134     0.001     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029)  (mean intra-corr 1.000)
  Family 2: 1987-09-15 Dortmund, West Germany (LB-00134)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-15 Dortmund, Germany Westfalenhalle 1 (LB-06029)       1.0kHz      -76.9dB      -0.00015
  1987-09-15 Dortmund, West Germany (LB-00134)       2.0kHz      -76.5dB      -0.00017
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [DISTINCT SOURCE] 1987-09-15 Dortmund, West Germany (LB-00134) (+58008 ppm speed offset, best cross-family corr 0.001): near-zero correlation to all other sources — entirely different recording
  1987-09-15  LB-00134/LB-06029: different_family -> different_family  [unchanged]
  Copying LB-00157: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) …
  Copying LB-05458: 1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458) …
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.8 GB (2 sources, largest 1:10:17)
=== INGEST / TRIM ===
  1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458): 14 tracks, 1:10:17
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): 14 tracks, 1:07:22

=== TRIM (performance envelope) ===
  1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458): trimmed 0:01:26 head, 0:00:52 tail -> performance 1:07:58
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): trimmed 0:01:30 head, 0:00:04 tail -> performance 1:05:48

=== ANCHORS (ref=1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458)) ===
  0:02:21, 0:08:16, 0:15:11, 0:19:45, 0:28:09, 0:33:22, 0:37:42, 0:39:58, 0:46:40, 0:51:47, 1:02:17, 1:05:40

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458)->1987-09-17 Treptower Festwiese - East Berlin (LB-00157): speed-unknown  speed ratio=1.030186 (+30186 ppm)  [conf=2.3]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-05458  LB-00157
  LB-05458     1.000     0.005
  LB-00157     0.005     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458)  (mean intra-corr 1.000)
  Family 2: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-17 East Berlin, East Germany, Treptower Festwiese (LB-05458)       1.0kHz      -82.2dB      -0.00002
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157)       2.0kHz      -81.0dB      +0.00025
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [DISTINCT SOURCE] 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) (+30186 ppm speed offset, best cross-family corr 0.005): near-zero correlation to all other sources — entirely different recording
  1987-09-17  LB-00157/LB-05458: different_family -> different_family  [unchanged]
  Copying LB-00157: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) …
  Copying LB-06108: 1987-09-17 East Berlin, East Germany (LB-06108) …
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.8 GB (2 sources, largest 1:09:53)
=== INGEST / TRIM ===
  1987-09-17 East Berlin, East Germany (LB-06108): 14 tracks, 1:09:53
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): 14 tracks, 1:07:22

=== TRIM (performance envelope) ===
  1987-09-17 East Berlin, East Germany (LB-06108): trimmed 0:01:15 head, 0:01:18 tail -> performance 1:07:20
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): trimmed 0:01:30 head, 0:00:04 tail -> performance 1:05:48

=== ANCHORS (ref=1987-09-17 East Berlin, East Germany (LB-06108)) ===
  0:01:49, 0:06:07, 0:15:26, 0:18:54, 0:24:50, 0:28:31, 0:38:16, 0:40:23, 0:47:13, 0:52:20, 0:56:45, 1:05:42

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-17 East Berlin, East Germany (LB-06108)->1987-09-17 Treptower Festwiese - East Berlin (LB-00157): speed-unknown  speed ratio=1.020559 (+20559 ppm)  [conf=1.9]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-06108  LB-00157
  LB-06108     1.000     0.004
  LB-00157     0.004     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-17 East Berlin, East Germany (LB-06108)  (mean intra-corr 1.000)
  Family 2: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-17 East Berlin, East Germany (LB-06108)       1.0kHz      -82.2dB      -0.00105
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157)       2.0kHz      -81.0dB      +0.00025
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [DISTINCT SOURCE] 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) (+20559 ppm speed offset, best cross-family corr 0.004): near-zero correlation to all other sources — entirely different recording
  1987-09-17  LB-00157/LB-06108: different_family -> different_family  [unchanged]
  Copying LB-00157: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) …
  Copying LB-11968: 1987-09-17 East Berlin, East Germany (LB-11968) …
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.8 GB (2 sources, largest 1:08:44)
=== INGEST / TRIM ===
  1987-09-17 East Berlin, East Germany (LB-11968): 15 tracks, 1:08:44
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): 14 tracks, 1:07:22

=== TRIM (performance envelope) ===
  1987-09-17 East Berlin, East Germany (LB-11968): trimmed 0:03:30 head, 0:00:07 tail -> performance 1:05:06
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157): trimmed 0:01:30 head, 0:00:04 tail -> performance 1:05:48

=== ANCHORS (ref=1987-09-17 East Berlin, East Germany (LB-11968)) ===
  0:02:01, 0:10:13, 0:10:55, 0:19:45, 0:24:47, 0:27:10, 0:34:03, 0:39:11, 0:45:38, 0:50:28, 0:54:49, 1:02:13

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-17 East Berlin, East Germany (LB-11968)->1987-09-17 Treptower Festwiese - East Berlin (LB-00157): speed-unknown  speed ratio=0.989414 (-10586 ppm)  [conf=1.5]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-11968  LB-00157
  LB-11968     1.000     0.004
  LB-00157     0.004     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-17 East Berlin, East Germany (LB-11968)  (mean intra-corr 1.000)
  Family 2: 1987-09-17 Treptower Festwiese - East Berlin (LB-00157)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-17 East Berlin, East Germany (LB-11968)       1.0kHz      -76.5dB      -0.00004
  1987-09-17 Treptower Festwiese - East Berlin (LB-00157)       2.0kHz      -81.0dB      +0.00025
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [DISTINCT SOURCE] 1987-09-17 Treptower Festwiese - East Berlin (LB-00157) (-10586 ppm speed offset, best cross-family corr 0.004): near-zero correlation to all other sources — entirely different recording
  1987-09-17  LB-00157/LB-11968: different_family -> different_family  [unchanged]
  Copying LB-00131: 1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131) …
  Copying LB-05156: 1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156) …
  curator lineage pairs loaded: 677 (from /home/tjenkins/Documents/losslessbob/data/losslessbob.db)
  est. peak RAM ~0.7 GB (2 sources, largest 0:59:38)
=== INGEST / TRIM ===
  1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156): 14 tracks, 0:56:32
  1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131): 14 tracks, 0:59:38

=== TRIM (performance envelope) ===
  1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156): trimmed 0:00:12 head, 0:00:08 tail -> performance 0:56:13
  1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131): trimmed 0:01:04 head, 0:00:00 tail -> performance 0:58:34

=== ANCHORS (ref=1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156)) ===
  0:01:44, 0:09:13, 0:13:43, 0:14:11, 0:20:22, 0:23:31, 0:29:13, 0:34:48, 0:40:19, 0:45:24, 0:47:37, 0:52:23

=== LAG CURVES / SPEED (vs ref) ===
  1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156)->1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131): speed-unknown  speed ratio=0.962638 (-37362 ppm)  [conf=2.3]

=== RESIDUAL CORRELATION MATRIX ===
  2 pair(s)/source(s) speed-unknown (v2 confidence < 6.0) — routed to fingerprint path only
          LB-05156  LB-00131
  LB-05156     1.000     0.005
  LB-00131     0.005     1.000

=== SECONDARY MATCH (windowed coverage + quiet-segment hiss + fingerprint) ===
  1 cross-family pair(s) — computing secondary evidence ...
  No secondary same-source evidence found.

=== CLUSTERS ===
  Family 1: 1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156)  (mean intra-corr 1.000)
  Family 2: 1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131)  (mean intra-corr 1.000)
  Distinct source families: 2

=== LINEAGE EVIDENCE (interpret manually) ===
    source   HF ceiling  noise floor  DC asymmetry
  1987-09-19 Rotterdam, The Netherlands, Sportpaleis Ahoy (LB-05156)       3.0kHz      -87.4dB      -0.00003
  1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131)       2.0kHz      -76.5dB      +0.00023
  (HF ceiling capped by 8000 Hz Nyquist at analysis_sr=16000; run lineage at native rate for real format discrimination)
  (DC asymmetry is a taper/equipment signature — not a reliable source-identity marker)

=== DIAGNOSTICS ===
  [DISTINCT SOURCE] 1987-09-19 Sportpaleis Ahoy, Rotterdam, The Netherlands (LB-00131) (-37362 ppm speed offset, best cross-family corr 0.005): near-zero correlation to all other sources — entirely different recording
  1987-09-19  LB-00131/LB-05156: different_family -> different_family  [unchanged]

Summary: 0 flipped to same_family, 6 unchanged (reassign to Cat 1/2/4), 0 missing on disk.

## Post-rerun frozen score (precision guard):
recall          39.2%       41.6%    +2.3
precision       98.6%       98.6%    +0.1
           candidate: tp=655 fn=920 fp=9 tn=1381
new FP: none  (precision preserved on frozen negatives)
CAT3 RERUN DONE 2026-07-02T17:44:30-05:00
