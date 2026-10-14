BUG-370: venue_geocoded pins venues in the wrong state/city (State Theater Portland ME pinned in Oregon)
Status: Open
File(s): backend/venue_gazetteer.py
Reported: 2026-10-14
Description: Found 2026-10-14 while checking TODO-346 Wikipedia links. venue_geocoded rows with wrong coordinates: 'State Theater | Portland | Maine' at 45.416,-122.664 (Oregon); 'State Theatre | Portland | United States' also Oregon; 'Cole Field House | College Park | Maryland' at 39.076,-77.184 (Rockville, ~22 km off); 'Coca Cola Roxy Theatre | Atlanta' ~10 km off. The pin feeds the dossier venue map and grades Wikidata matches, so a bad pin both misplaces the map and mis-links the venue. Audit: flag rows whose region disagrees with the state the coordinates fall in (same-name cities: Portland ME/OR, Columbia, Springfield...).
Root cause: Unknown
Fix: —
