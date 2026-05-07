The folder "Fixes for Vine 628" on this disc contains fixed FLAC versions 
of all shows from the original vine that had sector boundary errors.

The shows/folders affected are (all but last are on original DVD 2):
bd-91-06-08-milano-hg
bd-91-06-14-innsbruck-hg
bd-91-06-15-linz
bd-91-06-22-badmergetheim-hg
bd-1990-02-06-London-HG
bd-97-04-19-hartford-HG
bd-1997-03-31stjohn-HG-FLAC (on original DVD 1)


I fixed SBEs in 3 ways:
For tracks at the start of a side I added silence at the start
 (with  shntool pad -prepad filename)
For tracks in the middle of a side, I used the usual shntool method
 (shntool fix -s r *)
For tracks at the end of a side, I did not change SBEs - these SBEs
 are harmless unless you put another track after them on the same CD

The upshot is that if you want fixed versions, use the versions on this
DVD instead of the originals.  This means you would not use any of the 
original DVD 2, and you would use the 1997 St. John folder from this DVD,
instead of the original DVD 1.  All the other shows/folders on DVD 1 
are OK - no SBEs.