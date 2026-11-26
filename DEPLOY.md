# Public GeoWatch deployment

Use the GitHub repository as the source for both hosts. On Vercel select
`web` as the root directory and set `VITE_API_BASE` to the full HTTPS origin
of the Render service. The browser calls that API directly. Keep the API key
and Earth Engine credentials on Render.

On Render the root blueprint selects a free Python web service. Set
`GEOWATCH_CORS_ORIGINS` to the production Vercel HTTPS origin, and
`GEE_PROJECT_ID` to the registered project. Mount the server's Earth Engine
service-account JSON as a Render secret file named `ee-key.json`. The
service requires this file to start in production. Use an account with
Earth Engine Resource Viewer and Service Usage Consumer on that project.

The free deployment starts with one analysis at a time and a provisional
4 km² area cap to limit memory use. Stored results live on the instance's
ephemeral disk. Old report links can expire after sleep, restart, or deploy.
The server returns the active area cap to the map.

For a release check, open the frontend, verify the API's `/health`, submit a
small area through the map, wait for completion, and open its Change tab.
Health checks cover configuration and local storage. The live run checks
Earth Engine access and the analysis pipeline.
