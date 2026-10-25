// Live iNaturalist data: a browser port of the fetch/clip/status logic in export_gis.py

var INAT_API = 'https://api.inaturalist.org/v1/observations';
var PLANTAE_TAXON_ID = 47126;
var INAT_PAGE_DELAY_MS = 1000; // stay well under iNaturalist's rate limit

function sleep(ms) {
    return new Promise(function(resolve) {
        setTimeout(resolve, ms);
    });
}

// Ray-casting point-in-polygon test for one ring of [lng, lat] pairs
function ringContains(ring, x, y) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var xi = ring[i][0], yi = ring[i][1];
        var xj = ring[j][0], yj = ring[j][1];
        if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
            inside = !inside;
        }
    }
    return inside;
}

function polygonContains(geometry, lng, lat) {
    var polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
    return polygons.some(function(rings) {
        return ringContains(rings[0], lng, lat) &&
               !rings.slice(1).some(function(hole) { return ringContains(hole, lng, lat); });
    });
}

function polygonBounds(geometry) {
    var polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
    var lngs = [], lats = [];
    polygons.forEach(function(rings) {
        rings[0].forEach(function(coord) {
            lngs.push(coord[0]);
            lats.push(coord[1]);
        });
    });
    return {
        swlng: Math.min.apply(Math, lngs), nelng: Math.max.apply(Math, lngs),
        swlat: Math.min.apply(Math, lats), nelat: Math.max.apply(Math, lats)
    };
}

// === Species status lookup ================================================

// Match names across the status CSV and iNaturalist. Handles trailing whitespace,
// case and infraspecific markers so 'Artemisia tridentata ssp. wyomingensis'
// matches iNaturalist's 'Artemisia tridentata wyomingensis'.
function normalizeName(name) {
    return (name || '').trim().toLowerCase()
        .replace(/\b(ssp|subsp|var|f|forma)\.?\s+/g, '')
        .replace(/\s+/g, ' ');
}

function parseStatusCsv(text) {
    var lookup = {};
    text.split(/\r?\n/).slice(1).forEach(function(line) {
        var comma = line.lastIndexOf(',');
        if (comma < 0) {
            return;
        }
        var scientific = line.slice(0, comma).trim().replace(/^"|"$/g, '');
        var status = line.slice(comma + 1).trim();
        if (scientific && status) {
            lookup[normalizeName(scientific)] = status;
        }
    });
    return lookup;
}

// Exact match, then the binomial, then the genus. The genus step lets a single
// row cover a whole genus (Tamarix is listed at genus level in Idaho).
function getStatus(scientificName, lookup) {
    var key = normalizeName(scientificName);
    var parts = key.split(' ');
    var candidates = [key, parts.slice(0, 2).join(' '), parts[0]];
    for (var i = 0; i < candidates.length; i++) {
        if (candidates[i] && lookup[candidates[i]]) {
            return lookup[candidates[i]];
        }
    }
    return 'Not Assessed';
}

// === Fetch observations ====================================================

// Page through every verifiable plant observation in the polygon's bounding box and
// clip to the polygon locally (iNaturalist has no arbitrary-polygon filter). Paging
// uses id_above rather than page numbers so records can't be skipped or duplicated
// if observations are added while we are reading.
async function fetchInatObservations(geometry, onProgress) {
    var bounds = polygonBounds(geometry);
    var inside = [];
    var idAbove = 0;
    var fetched = 0;

    while (true) {
        var params = new URLSearchParams({
            taxon_id: PLANTAE_TAXON_ID,
            verifiable: 'true',
            geo: 'true',
            per_page: 200,
            order_by: 'id',
            order: 'asc',
            id_above: idAbove,
            nelat: bounds.nelat, nelng: bounds.nelng,
            swlat: bounds.swlat, swlng: bounds.swlng
        });
        var response = await fetch(INAT_API + '?' + params);
        if (!response.ok) {
            throw new Error('iNaturalist returned HTTP ' + response.status);
        }
        var results = (await response.json()).results;
        if (!results.length) {
            break;
        }

        fetched += results.length;
        results.forEach(function(observation) {
            var coords = observation.geojson && observation.geojson.coordinates;
            if (coords && polygonContains(geometry, coords[0], coords[1])) {
                inside.push(observation);
            }
        });
        idAbove = results[results.length - 1].id;
        if (onProgress) {
            onProgress(fetched, inside.length);
        }

        if (results.length < 200) {
            break; // short page: that was the last one
        }
        await sleep(INAT_PAGE_DELAY_MS);
    }
    return inside;
}

// Shape an API observation into the record format used by markers.json
function toMarker(observation, statusLookup) {
    var taxon = observation.taxon || {};
    var user = observation.user || {};
    var photos = observation.photos || [];
    var scientific = taxon.name || 'Unknown';
    var coords = observation.geojson.coordinates;

    return {
        lat: Number(coords[1].toFixed(6)),
        lng: Number(coords[0].toFixed(6)),
        id: observation.id,
        name: scientific,
        common_name: taxon.preferred_common_name || observation.species_guess || '',
        taxon_rank: taxon.rank || '',
        status: getStatus(scientific, statusLookup),
        observed_on: observation.observed_on || '',
        quality_grade: observation.quality_grade || '',
        captive: !!observation.captive,
        coord_obscured: !!observation.obscured,
        positional_accuracy_m: observation.positional_accuracy === undefined ? null : observation.positional_accuracy,
        observer: user.login || '',
        license: observation.license_code || '',
        photo_url: photos.length ? (photos[0].url || '').replace('square', 'medium') : '',
        inat_url: observation.uri || ''
    };
}

// Fetch live data. Resolves to a list of markers sorted like markers.json.
async function loadLiveMarkers(fieldAreaGeoJson, onProgress) {
    var geometry = fieldAreaGeoJson.features[0].geometry;
    var statusResponse = await fetch('data/species_status.csv');
    if (!statusResponse.ok) {
        throw new Error('Could not load data/species_status.csv');
    }
    var statusLookup = parseStatusCsv(await statusResponse.text());

    var observations = await fetchInatObservations(geometry, onProgress);
    var markers = observations.map(function(observation) {
        return toMarker(observation, statusLookup);
    });
    markers.sort(function(a, b) {
        return a.name.localeCompare(b.name) ||
               a.observed_on.localeCompare(b.observed_on) ||
               a.id - b.id;
    });
    return markers;
}

// One row per taxon, matching species_summary.csv from export_gis.py
function buildSpeciesSummary(markers) {
    var byTaxon = {};
    markers.forEach(function(marker) {
        (byTaxon[marker.name] = byTaxon[marker.name] || []).push(marker);
    });

    return Object.keys(byTaxon).sort().map(function(name) {
        var group = byTaxon[name];
        var dates = group.map(function(m) { return m.observed_on; }).filter(Boolean).sort();
        var withCommon = group.find(function(m) { return m.common_name; });
        return {
            scientific_name: name,
            common_name: withCommon ? withCommon.common_name : '',
            status: group[0].status,
            taxon_rank: group[0].taxon_rank,
            observation_count: group.length,
            research_grade_count: group.filter(function(m) { return m.quality_grade === 'research'; }).length,
            first_observed_on: dates.length ? dates[0] : '',
            last_observed_on: dates.length ? dates[dates.length - 1] : '',
            obscured_count: group.filter(function(m) { return m.coord_obscured; }).length
        };
    });
}
