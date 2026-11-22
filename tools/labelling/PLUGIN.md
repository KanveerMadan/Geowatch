# QGIS Item 21 review tools

## Install on macOS

1. In QGIS LTR, open **Settings → User Profiles → Open Active Profile Folder**. The standard profile is `default`. Quit QGIS.
2. Open Terminal in the `gw-labeltools` worktree. Run the following commands for the standard profile. If you use another profile, set `profile_dir` to the folder QGIS opened. The link lets QGIS use the branch's plugin, firewall, validator and frozen training roster together. Keep this worktree available.

   ```sh
   profile_dir="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default"
   mkdir -p "$profile_dir/python/plugins"
   plugin_link="$profile_dir/python/plugins/geowatch_item21"
   if test -e "$plugin_link" || test -L "$plugin_link"; then
     ls -ld "$plugin_link"
   else
     ln -s "$PWD/tools/labelling/geowatch_item21" "$plugin_link"
   fi
   ```

   The command displays an existing destination for inspection. If it already links to this worktree, installation is complete. Each user profile has its own plugins and review history.
3. Restart QGIS. Open **Plugins → Manage and Install Plugins → Installed**, enable **GeoWatch Item 21 review**, open a generated `label_project.qgz`, then choose **Plugins → GeoWatch → GeoWatch · Item 21** to show the review panel. Click the map for keyboard focus. QGIS 3.44 LTR on macOS was used for the desktop integration test.

## Review a tile

Press **]** for a suggested polygon. Inspect its edges on the high-resolution photograph and read the source and note. A buffered road may cover dirt or roadside vegetation. Toggle the suggestion layer or group with the Layers panel eye/checkbox to inspect the actual image. Hint layers only guide your eyes. Each accepted polygon needs an explicit action.

| Shortcut | Action |
|---|---|
| **]** / **[** | Next / previous unchecked suggestion, select it and zoom |
| **A** | Accept the displayed geometry and class, then advance |
| **E** | Copy the displayed polygon, select the copy and activate the vertex tool. A vertex or class change sets its provenance to edited. |
| **R** | Reject and advance. Use **Reopen rejection** to return a rejected suggestion to the queue. |
| **1, 2, 3, 4, 5** | Built, paved, bare, vegetation, water |
| **6, 7, 8, 9, 0** | Mixed water/vegetation, snow/ice, solar, full shadow, unsure |
| **D** | Trace a polygon with the selected class. Left click adds vertices, right click finishes. QGIS snapping applies. |
| **F** | Open the selected final label's normal form, including partial shadow, rooftop solar, class and note |
| **U** | Show a snapshot of the uncovered area from the current edits. Toggle off and on after changes. |
| **T** | Start or stop the active session. Enter the labeller name on first use. |
| **Mark tile done** | Save pending edits on confirmation, run the tile validator, and open its detailed report. A successful check records completion in this profile. |

Number keys update one selected final label while its layer is active. While drawing, or with a suggestion active, they choose the class for the next trace. Press **F** to record shadow or rooftop flags. During tracing, use the class in the guide that best describes the visible surface. Record ambiguous surface as unsure, deep unidentifiable shadow as full shadow, and a recognisable shaded surface as its class with the partial-shadow flag.

QGIS holds new labels in its normal edit buffer until you choose **Save Layer Edits**. Save regularly. Undo and rollback are available during the session. New provenance columns are added on the first explicit review or drawing edit. Earlier polygons keep their original source status; the validator lists missing origins. Hand-drawn polygons have empty external source fields. A kept or edited suggestion retains its original source, upstream object ID, version and candidate ID. Use the plugin's **D** tool to attribute a manual trace. Pasted/imported polygons need explicit provenance review. Validation and blind re-traces follow the from-scratch workflow.

**Time and completion.** Only **T** changes the timing record in `metadata.json`. Stop the timer before taking a break or closing QGIS. Reopen the same tile and press **T** to stop a previously started session. Active elapsed time includes breaks while the timer is running. The metadata preserves individual start/stop sessions and earlier logged minutes. On first use of **Mark tile done**, select the GeoWatch environment's Python executable (the file `geowatch-env/bin/python` in the environment you already use). Use **Show Details** for geometry, coverage, provenance and class warnings. Rejections and successful checks are kept in `geowatch/item21_review.sqlite` in the QGIS profile. Unchecked suggestions can remain unused. Finishing requires coverage and valid labels in the independent validator.
