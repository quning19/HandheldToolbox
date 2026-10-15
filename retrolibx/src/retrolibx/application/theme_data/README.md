# Theme adaptation rules

Profiles, selected batch rules, and the active badge parameters are retained from the user's local `FrontendThemeConverter/config` project (2026-10-15). `theme_badges.py` retains its badge drawing functions; desktop paths use the current Windows Fonts directory.

The desktop service supplies source/output paths from the software workspace. These files contain no theme artwork and do not require the sibling project at runtime. Existing per-theme slot choices, optional/required slots, directory assets, copy-only suffixes, and metadata directories are preserved. Additional user categories inherit a configured mother; unavailable required assets stop conversion rather than produce an uploadable incomplete theme.

The original batch scope remains unchanged for existing baseline categories. Newly registered independent categories use that profile's full slot set. The complete platform XML remains maintained in `frontend_platforms/custom_systems-PG`; these profiles do not introduce a second platform definition.
