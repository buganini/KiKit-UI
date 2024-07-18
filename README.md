# Notice
You probably need to update the python executable path at the first line of ui.py

Tested with KiCad 7.0.10 and KiKit 1.5.1

# Tight Frame + Auto Tab + Auto Cut
![UI](screenshots/tight_frame_autotab_autocut.png)
## Output
![Output](screenshots/tight_frame_autotab_autocut_output.png)
## 3D Output
![3D Output](screenshots/tight_frame_autotab_autocut_output_3d.png)

# Tight Frame + Auto Tab + Mousebites
![UI](screenshots/tight_frame_autotab_mousebites.png)

# Loose Frame + Auto Tab + Mousebites
![UI](screenshots/loose_frame_autotab_mousebites.png)
## 3D Output
![3D Output](screenshots/loose_frame_autotab_mousebites_output_3d.png)

# Auto Tab
Tab position candidates is determined by PCB Edge / `max_tab_spacing`, prioritized by divided edge length (smaller first), and skipped if there is an nearby (distance < `max_tab_spacing/3`) cadidate with higher priority.

In the below image, small red dots are tab position candidates, bigger red circle are selected candidates, the two rectangles are two half-bridge tabs.
![Auto Tab](screenshots/auto_tab_selection.png)

# ToDo
* Manual tabbing
* Arbitrary rotation