BUG-394: wtrf_retire deleted overlay folders still used by a second live torrent (23 folders)
Status: Open
File(s): backend/wtrf_repost.py
Reported: 2026-11-25
Description: Two WTRF topics can post the same torrent name, so two infohashes seed from one overlay folder. retire() deleted the folder for the incomplete one and its UPDATE by seed_folder also marked the live twin's wtrf_downloads row retired. 1,090-run 2026-11-25 hit 23 folders (20 complete twins now seeding from missing files). Collection untouched (unlinks only; LB-02637 md5-verified 33/33). Code fixed same day; data repair pending tj's choice.
Root cause: Unknown
Fix: —
