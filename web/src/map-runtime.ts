// SPDX-License-Identifier: AGPL-3.0-or-later
// Vite must bundle the worker's shared ESM imports. A raw ?url is insufficient.
import * as maplibre from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
maplibre.setWorkerUrl(workerUrl);
export default maplibre;
