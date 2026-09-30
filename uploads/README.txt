Packs installed from the admin page land here. The .json packs are safe to empty.
The server also writes its runtime state here: unlock-codes.db (the codes
database, created by the admin page) and unlock-redemptions.jsonl. Neither is
ever committed. See docs/unlock-codes.md.
