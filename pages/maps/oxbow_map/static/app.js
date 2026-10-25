// Oxbow Field Area Map JavaScript

// Global variables
var map = null;
var allMarkers = [];
var visibleMarkers = [];
var observationData = {};
var markersLayer = null;
var boundaryLayer = null;
var fieldAreaProps = null;
var currentTaxonData = null;
var observationTable = null;
var observationMarkers = []; // Populated from data/markers.json

// Map status to CSS class name and legend color
var statusToClass = {
    "Native": "marker-native",
    "Non-Native": "marker-non-native",
    "Invasive": "marker-invasive",
    "Noxious": "marker-noxious",
    "Not Assessed": "marker-not-assessed"
};

var statusToColor = {
    "Native": "#2e9e4f",
    "Non-Native": "#e0b020",
    "Invasive": "#e8801c",
    "Noxious": "#d63031",
    "Not Assessed": "#8e9aa0"
};

var qualityLabels = {
    "research": "Research Grade",
    "needs_id": "Needs ID"
};

var LEAFLET_IMAGES = 'https://unpkg.com/leaflet@1.9.4/dist/images/';

// Escape text before it goes into innerHTML (observer names and species guesses are user-entered)
function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function statusOf(observation) {
    return statusToClass[observation.status] ? observation.status : "Not Assessed";
}

function yearOf(observation) {
    return parseInt((observation.observed_on || '').slice(0, 4), 10);
}

// Function to initialize observation data
function initializeObservationData(markers) {
    observationMarkers = markers;
    // Create observation data lookup
    observationMarkers.forEach(function(marker) {
        observationData[marker.id] = marker;
    });
    // Populate taxa for autocomplete
    var taxa = {};
    markers.forEach(function(marker) {
        taxa[marker.name] = marker.common_name || '';
    });
    allTaxa = Object.keys(taxa).sort().map(function(name) {
        return { name: name, common: taxa[name] };
    });
}

// Build one marker icon per status. The class recolors the stock blue pin.
function createStatusIcon(cssClass) {
    return L.icon({
        iconUrl: LEAFLET_IMAGES + 'marker-icon.png',
        iconRetinaUrl: LEAFLET_IMAGES + 'marker-icon-2x.png',
        shadowUrl: LEAFLET_IMAGES + 'marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41],
        className: cssClass
    });
}

var statusIcons = {};
Object.keys(statusToClass).forEach(function(status) {
    statusIcons[status] = createStatusIcon(statusToClass[status]);
});

// Initialize map
function initializeMap() {
    // Initialize the map
    map = L.map('map');

    // Add tile layers
    var openStreetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    });

    var esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Esri',
        maxZoom: 19
    });

    // Add default layer
    esriSatellite.addTo(map);

    // Field area boundary
    boundaryLayer = L.geoJSON(fieldAreaGeoJson, {
        style: { color: '#3498db', weight: 2.5, fillColor: '#3498db', fillOpacity: 0.08 },
        interactive: false
    }).addTo(map);

    // Create layer control
    var baseLayers = {
        "OpenStreetMap": openStreetMap,
        "Satellite": esriSatellite
    };
    var overlays = {
        "Field Area": boundaryLayer
    };
    L.control.layers(baseLayers, overlays).addTo(map);

    // Add scale
    L.control.scale().addTo(map);

    // Add custom center button
    var centerControl = L.Control.extend({
        options: {
            position: 'topleft'
        },
        onAdd: function (map) {
            var container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-custom');
            container.style.backgroundColor = 'white';
            container.style.width = '30px';
            container.style.height = '30px';
            container.style.cursor = 'pointer';
            container.innerHTML = '⊕'; // crosshairs symbol
            container.style.fontSize = '24px';
            container.style.fontWeight='Bold';
            container.style.textAlign = 'center';
            container.style.lineHeight = '30px';
            container.style.border = '2px solid rgba(0,0,0,0.2)';
            container.style.borderRadius = '4px';
            container.title = 'Reset map view';

            // Add hover effects
            container.onmouseover = function() {
                container.style.backgroundColor = '#f4f4f4';
            };
            container.onmouseout = function() {
                container.style.backgroundColor = 'white';
            };

            container.onclick = function(){
                resetMapView();
            }
            return container;
        }
    });
    map.addControl(new centerControl());

    // Create markers layer group
    markersLayer = L.layerGroup().addTo(map);

    // Add markers
    addMarkers();

    // Frame the field area
    resetMapView();

    // Build legend and update statistics
    buildLegend();
    updateStatistics();

    // Add window resize handler
    window.addEventListener('resize', function() {
        setTimeout(function() {
            if (map) {
                map.invalidateSize();
            }
        }, 100);
    });
}

// Add markers to map
function addMarkers() {
    observationMarkers.forEach(function(markerData) {
        var marker = L.marker([markerData.lat, markerData.lng], {
            icon: statusIcons[statusOf(markerData)],
            title: markerData.name,
            alt: markerData.name,
            observationId: markerData.id
        });

        marker.on('click', function() {
            selectObservation(markerData.id);
        });

        markersLayer.addLayer(marker);

        allMarkers.push(marker);
        visibleMarkers.push(marker);
    });
}

// Select an observation: ring it on the map, fill the info panel and taxon table
function selectObservation(observationId) {
    var observation = observationData[observationId];
    if (observation) {
        // Update the currently selected observation and apply styling
        currentlySelectedObservation = observationId;
        applySelectedObservationStyling();
        updateInfoPanel(observation);
        showTaxonTable(observation);
    } else {
        console.error('Observation not found:', observationId);

        // Clear the currently selected observation
        currentlySelectedObservation = null;
        applySelectedObservationStyling();
        clearInfoPanel();
    }
}

// Function to update info panel
function updateInfoPanel(observation) {
    var status = statusOf(observation);
    var accuracy = observation.positional_accuracy_m;
    var notes = [];
    if (observation.captive) {
        notes.push('Planted or cultivated');
    }
    if (observation.coord_obscured) {
        notes.push('Coordinates obscured by iNaturalist');
    }

    document.getElementById('observationInfo').innerHTML = `
        ${observation.photo_url ? `<img src="${escapeHtml(observation.photo_url)}" alt="${escapeHtml(observation.name)}">` : ''}
        <h3>${escapeHtml(observation.name)}</h3>
        <p class="common-name">${escapeHtml(observation.common_name || 'No common name')}</p>
        <span class="status-pill" style="background: ${statusToColor[status]}">${escapeHtml(status)}</span>
        <p><strong>Rank:</strong> ${escapeHtml(observation.taxon_rank || 'Unknown')}</p>
        <p><strong>Observed:</strong> ${escapeHtml(observation.observed_on || 'Unknown')}</p>
        <p><strong>Quality:</strong> ${escapeHtml(qualityLabels[observation.quality_grade] || observation.quality_grade || 'Unknown')}</p>
        <p><strong>Observer:</strong> ${escapeHtml(observation.observer || 'Unknown')}</p>
        <p><strong>Coordinates:</strong> ${observation.lat.toFixed(5)}, ${observation.lng.toFixed(5)}</p>
        <p><strong>Accuracy:</strong> ${accuracy === null || accuracy === undefined ? 'Not reported' : accuracy + ' m'}</p>
        <p><strong>License:</strong> ${escapeHtml(observation.license || 'All rights reserved')}</p>
        ${notes.length ? `<p><em>${escapeHtml(notes.join('; '))}</em></p>` : ''}
        <p><a href="${escapeHtml(observation.inat_url)}" target="_blank" rel="noopener">View observation ${escapeHtml(observation.id)} on iNaturalist</a></p>
    `;
}

function clearInfoPanel() {
    document.getElementById('observationInfo').innerHTML = '<p class="no-selection">Click on an observation marker to view details</p>';
    document.getElementById('tableContainer').style.display = 'none';
    currentTaxonData = null;
}

// Show every observation of the selected taxon in a table
function showTaxonTable(observation) {
    var taxonObservations = observationMarkers.filter(function(other) {
        return other.name === observation.name;
    });

    currentTaxonData = {
        name: observation.name,
        observations: taxonObservations
    };

    document.getElementById('tableContainer').style.display = 'block';
    document.getElementById('tableTitle').textContent =
        `Observations - ${observation.name} (${taxonObservations.length})`;

    // Destroy existing table if it exists
    if (observationTable) {
        observationTable.destroy();
    }

    // Create new Handsontable
    var container = document.getElementById('observationTable');
    observationTable = new Handsontable(container, {
        data: taxonObservations,
        colHeaders: ['Observed', 'Observer', 'Quality'],
        columns: [
            { data: 'observed_on', type: 'text', readOnly: true },
            { data: 'observer', type: 'text', readOnly: true },
            {
                data: 'quality_grade',
                type: 'text',
                readOnly: true,
                renderer: function(instance, td, row, col, prop, value) {
                    td.textContent = qualityLabels[value] || value || '';
                    return td;
                }
            }
        ],
        rowHeaders: false,
        width: '100%',
        height: 250,
        licenseKey: 'non-commercial-and-evaluation',
        stretchH: 'all',
        autoColumnSize: true,
        manualColumnResize: true,
        columnSorting: true,
        contextMenu: ['copy'],
        copyPaste: true,
        afterOnCellMouseDown: function(event, coords) {
            if (coords.row < 0) {
                return; // header click sorts the column
            }
            var clicked = this.getSourceDataAtRow(this.toPhysicalRow(coords.row));
            var marker = findMarker(clicked.id);
            if (marker && markersLayer.hasLayer(marker)) {
                map.panTo(marker.getLatLng());
            }
            currentlySelectedObservation = clicked.id;
            applySelectedObservationStyling();
            updateInfoPanel(clicked);
        }
    });
}

function findMarker(observationId) {
    return allMarkers.find(function(marker) {
        return marker.options.observationId === observationId;
    });
}

// Action button functions
function resetMapView() {
    if (map && boundaryLayer) {
        map.fitBounds(boundaryLayer.getBounds(), {padding: [20, 20]});
    }
}

function fitMapToBounds() {
    if (!markersLayer || visibleMarkers.length === 0) return;

    var group = L.featureGroup(visibleMarkers);
    map.fitBounds(group.getBounds(), {padding: [20, 20], maxZoom: 18});
}

// Unified filtering function that applies ALL active filters
function applyAllFilters(preserveSelection) {
    var selectedStatus = document.getElementById('statusFilter').value;
    var selectedQuality = document.getElementById('qualityFilter').value;
    var minYear = parseInt(document.getElementById('minYear').value, 10);
    var maxYear = parseInt(document.getElementById('maxYear').value, 10);
    var searchTerm = document.getElementById('speciesSearch').value.toLowerCase().trim();

    // Clear selection unless explicitly preserving it
    if (!preserveSelection) {
        currentlySelectedObservation = null;
        clearInfoPanel();
    }

    // Reset visible markers array
    visibleMarkers = [];

    // Filter markers without destroying them to preserve event handlers
    allMarkers.forEach(function(marker) {
        var observation = observationData[marker.options.observationId];
        var includeMarker = true;

        // Filter by Status (if selected)
        if (selectedStatus && statusOf(observation) !== selectedStatus) {
            includeMarker = false;
        }

        // Filter by Quality Grade (if selected)
        if (includeMarker && selectedQuality && observation.quality_grade !== selectedQuality) {
            includeMarker = false;
        }

        // Filter by Year Observed (if either from or to year is specified)
        if (includeMarker && (!isNaN(minYear) || !isNaN(maxYear))) {
            var effectiveMinYear = isNaN(minYear) ? -Infinity : minYear;
            var effectiveMaxYear = isNaN(maxYear) ? Infinity : maxYear;
            var year = yearOf(observation);

            if (isNaN(year) || year < effectiveMinYear || year > effectiveMaxYear) {
                includeMarker = false;
            }
        }

        // Filter by Species (if search term is provided)
        if (includeMarker && searchTerm) {
            var haystack = (observation.name + ' ' + (observation.common_name || '')).toLowerCase();
            if (!haystack.includes(searchTerm)) {
                includeMarker = false;
            }
        }

        // Show or hide marker based on filter results
        if (includeMarker) {
            if (!markersLayer.hasLayer(marker)) {
                markersLayer.addLayer(marker);
            }
            visibleMarkers.push(marker);
        } else {
            if (markersLayer.hasLayer(marker)) {
                markersLayer.removeLayer(marker);
            }
        }
    });

    // Apply selected observation styling
    applySelectedObservationStyling();

    updateStatistics();
}

// Track currently selected observation and ring marker
var currentlySelectedObservation = null;
var selectionRingMarker = null;

// Function to apply red ring styling to the currently selected observation
function applySelectedObservationStyling() {
    // Remove existing ring marker if it exists
    if (selectionRingMarker) {
        map.removeLayer(selectionRingMarker);
        selectionRingMarker = null;
    }

    // If there's a currently selected observation, add the red ring to it
    if (currentlySelectedObservation !== null) {
        var selectedMarker = findMarker(currentlySelectedObservation);

        if (selectedMarker && markersLayer.hasLayer(selectedMarker)) {
            // Create a custom ring icon that circles the base of the pin
            var ringIcon = L.divIcon({
                className: 'selection-ring-marker',
                html: '<div class="selection-ring"></div>',
                iconSize: [24, 24],
                iconAnchor: [17.5, 20] // Ring is 35px wide: centered horizontally, 2.5px above the pin's tip
            });

            // Create the ring marker at the same position
            selectionRingMarker = L.marker(selectedMarker.getLatLng(), {
                icon: ringIcon,
                interactive: false, // Don't interfere with clicks
                zIndexOffset: -1000 // Put it behind the pins
            }).addTo(map);
        }
    }
}

// Individual filter functions now call the unified filter
function filterByStatus() {
    applyAllFilters();
}

function filterByQuality() {
    applyAllFilters();
}

function filterByYear() {
    applyAllFilters();
}

var currentSuggestionIndex = -1;
var allTaxa = [];

function handleSpeciesSearch() {
    var searchTerm = document.getElementById('speciesSearch').value.toLowerCase().trim();
    var suggestionsContainer = document.getElementById('speciesSuggestions');

    if (searchTerm.length === 0) {
        // Hide suggestions and apply all other filters
        suggestionsContainer.style.display = 'none';
        applyAllFilters();
        return;
    }

    // Filter taxa based on search term (scientific or common name)
    var matchingTaxa = allTaxa.filter(function(taxon) {
        return taxon.name.toLowerCase().includes(searchTerm) ||
               taxon.common.toLowerCase().includes(searchTerm);
    });

    if (matchingTaxa.length > 0) {
        // Show suggestions dropdown
        showSuggestions(matchingTaxa);
    } else {
        // Hide suggestions if no matches
        suggestionsContainer.style.display = 'none';
    }

    // Apply all filters including search term (shows no results if nothing matches)
    applyAllFilters();
}

function showSuggestions(suggestions) {
    var suggestionsContainer = document.getElementById('speciesSuggestions');
    suggestionsContainer.innerHTML = '';

    // Limit to first 10 suggestions
    suggestions.slice(0, 10).forEach(function(suggestion) {
        var suggestionItem = document.createElement('div');
        suggestionItem.className = 'suggestion-item';
        suggestionItem.dataset.name = suggestion.name;

        var scientific = document.createElement('em');
        scientific.textContent = suggestion.name;
        suggestionItem.appendChild(scientific);

        if (suggestion.common) {
            var common = document.createElement('span');
            common.className = 'suggestion-common';
            common.textContent = suggestion.common;
            suggestionItem.appendChild(common);
        }

        suggestionItem.onclick = function() {
            selectSpecies(suggestion.name);
        };

        suggestionsContainer.appendChild(suggestionItem);
    });

    suggestionsContainer.style.display = 'block';
    currentSuggestionIndex = -1;
}

function selectSpecies(speciesName) {
    document.getElementById('speciesSearch').value = speciesName;
    document.getElementById('speciesSuggestions').style.display = 'none';

    // Apply all filters with the selected species, preserving selection
    applyAllFilters(true);

    // Frame the species on the map and show the first visible observation
    var speciesMarkers = visibleMarkers.filter(function(marker) {
        return marker.options.title === speciesName;
    });
    if (speciesMarkers.length > 0) {
        map.fitBounds(L.featureGroup(speciesMarkers).getBounds(), {padding: [60, 60], maxZoom: 18});
        selectObservation(speciesMarkers[0].options.observationId);
    }
}

function clearFilters() {
    document.getElementById('statusFilter').value = '';
    document.getElementById('qualityFilter').value = '';
    document.getElementById('minYear').value = '';
    document.getElementById('maxYear').value = '';
    document.getElementById('speciesSearch').value = '';
    document.getElementById('speciesSuggestions').style.display = 'none';

    // Apply all filters (which will show all markers since filters are cleared)
    applyAllFilters();
}

function buildLegend() {
    var legend = document.getElementById('legend');
    legend.innerHTML = '';

    Object.keys(statusToClass).forEach(function(status) {
        var item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
            <span class="legend-swatch" style="background: ${statusToColor[status]}"></span>
            <span class="legend-name">${escapeHtml(status)}</span>
            <span id="legend-count-${escapeHtml(status.replace(/\W+/g, '-'))}"></span>
        `;
        legend.appendChild(item);
    });
}

function updateStatistics() {
    document.getElementById('visibleObservations').textContent = visibleMarkers.length;

    // Count visible observations by status for the legend
    var counts = {};
    Object.keys(statusToClass).forEach(function(status) {
        counts[status] = 0;
    });

    var taxa = {};
    var years = [];
    visibleMarkers.forEach(function(marker) {
        var observation = observationData[marker.options.observationId];
        counts[statusOf(observation)]++;
        taxa[observation.name] = true;
        if (!isNaN(yearOf(observation))) {
            years.push(yearOf(observation));
        }
    });

    Object.keys(counts).forEach(function(status) {
        var countElement = document.getElementById('legend-count-' + status.replace(/\W+/g, '-'));
        if (countElement) {
            countElement.textContent = counts[status];
        }
    });

    document.getElementById('visibleTaxa').textContent = Object.keys(taxa).length;

    if (years.length > 0) {
        var minYear = Math.min.apply(Math, years);
        var maxYear = Math.max.apply(Math, years);
        document.getElementById('yearRange').textContent = minYear === maxYear ? minYear : minYear + '-' + maxYear;
    } else {
        document.getElementById('yearRange').textContent = 'No data';
    }
}

function csvCell(value) {
    var text = value === null || value === undefined ? '' : String(value);
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

var observationCsvColumns = [
    ['obs_id', 'id'],
    ['scientific_name', 'name'],
    ['common_name', 'common_name'],
    ['taxon_rank', 'taxon_rank'],
    ['status', 'status'],
    ['observed_on', 'observed_on'],
    ['quality_grade', 'quality_grade'],
    ['captive', 'captive'],
    ['coord_obscured', 'coord_obscured'],
    ['positional_accuracy_m', 'positional_accuracy_m'],
    ['observer', 'observer'],
    ['license', 'license'],
    ['latitude', 'lat'],
    ['longitude', 'lng'],
    ['inat_url', 'inat_url']
];

function observationsToCSV(observations) {
    var csvContent = observationCsvColumns.map(function(column) {
        return column[0];
    }).join(',') + '\n';

    observations.forEach(function(observation) {
        csvContent += observationCsvColumns.map(function(column) {
            return csvCell(observation[column[1]]);
        }).join(',') + '\n';
    });
    return csvContent;
}

function exportVisibleData() {
    var observations = visibleMarkers.map(function(marker) {
        return observationData[marker.options.observationId];
    });
    downloadCSV(observationsToCSV(observations), 'visible_observations.csv');
}

function downloadCSV(content, filename) {
    var blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function exportTaxonData() {
    if (!currentTaxonData) {
        alert('No taxon data to export');
        return;
    }

    var filename = currentTaxonData.name.replace(/\W+/g, '_') + '_observations.csv';
    downloadCSV(observationsToCSV(currentTaxonData.observations), filename);
}

function exportSpeciesSummary() {
    var summary = buildSpeciesSummary(observationMarkers);
    var columns = Object.keys(summary[0]);
    var csvContent = columns.join(',') + '\n';
    summary.forEach(function(row) {
        csvContent += columns.map(function(column) {
            return csvCell(row[column]);
        }).join(',') + '\n';
    });
    downloadCSV(csvContent, 'oxbow_species_summary.csv');
}

function downloadFile(href, filename) {
    // Create a link to download a file served next to the page
    var link = document.createElement('a');
    link.href = href;
    link.download = filename;
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function handleMultipleExports() {
    // Get selected export options from MultiSelect
    var selectedExports = [];

    // The MultiSelect library creates hidden inputs with name pattern like "multi-select-[id][]"
    var multiSelectElement = document.querySelector('.multi-select');
    if (multiSelectElement) {
        var hiddenInputs = multiSelectElement.querySelectorAll('input[type="hidden"]');
        hiddenInputs.forEach(function(input) {
            if (input.value) {
                selectedExports.push(input.value);
            }
        });
    }

    if (selectedExports.length === 0) {
        alert('Please select at least one export option');
        return;
    }

    // Execute selected exports with small delays to avoid browser blocking
    selectedExports.forEach(function(exportType, index) {
        setTimeout(function() {
            switch(exportType) {
                case 'visible-observations':
                    exportVisibleData();
                    break;
                case 'species-summary':
                    exportSpeciesSummary();
                    break;
                case 'field-area':
                    downloadFile('data/field_area.geojson', 'oxbow_field_area.geojson');
                    break;
                case 'gis-package':
                    downloadFile('data/oxbow_field_area_gis.zip', 'oxbow_field_area_gis.zip');
                    break;
                default:
                    console.warn('Unknown export type:', exportType);
            }
        }, index * 500); // 500ms delay between exports
    });
}

// Fetch observation data and field area boundary from JSON files
var fieldAreaGeoJson = null;
var dataSourceLabel = '';

function fetchJson(url) {
    return fetch(url).then(function(response) {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status} for ${url}`);
        }
        return response.json();
    });
}

function setDataSource(text) {
    document.getElementById('dataSource').textContent = text;
    document.getElementById('mapLoadingText').textContent = text;
}

// Load observations live from iNaturalist, falling back to the snapshot in data/markers.json
async function fetchObservationData() {
    var markers = null;
    try {
        fieldAreaGeoJson = await fetchJson('data/field_area.geojson');
        fieldAreaProps = fieldAreaGeoJson.features[0].properties;
        document.getElementById('fieldArea').textContent = fieldAreaProps.area_acres.toFixed(1) + ' acres';
    } catch (error) {
        console.error('Error fetching field area:', error);
        alert('Error loading the field area. Serve this folder over HTTP (sh test.sh) rather than opening the file directly.');
        return null;
    }

    setDataSource('Fetching from iNaturalist...');
    try {
        markers = await loadLiveMarkers(fieldAreaGeoJson, function(fetched, inside) {
            setDataSource('Fetching from iNaturalist... ' + inside + ' found');
        });
        dataSourceLabel = 'iNaturalist (live, ' + new Date().toLocaleTimeString() + ')';
    } catch (error) {
        console.warn('Live iNaturalist fetch failed, using the saved snapshot:', error);
        try {
            markers = await fetchJson('data/markers.json');
            dataSourceLabel = 'Saved snapshot (iNaturalist unreachable)';
        } catch (snapshotError) {
            console.error('Error fetching observation data:', snapshotError);
            alert('Error loading observation data from iNaturalist or the saved snapshot.');
            return null;
        }
    }

    initializeObservationData(markers);
    document.getElementById('totalObservations').textContent = markers.length;
    setDataSource(dataSourceLabel);
    return markers;
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    fetchObservationData().then(function(data) {
        if (!data) {
            return;
        }
        initializeMap();
        document.getElementById('mapLoading').style.display = 'none';
        // Add keyboard navigation and click-outside handler for autocomplete
        addAutocompleteEventHandlers();
    });
});

// Add keyboard navigation and click-outside handler for autocomplete
function addAutocompleteEventHandlers() {
    var searchInput = document.getElementById('speciesSearch');
    var suggestionsContainer = document.getElementById('speciesSuggestions');

    // Keyboard navigation
    searchInput.addEventListener('keydown', function(e) {
        var suggestions = suggestionsContainer.querySelectorAll('.suggestion-item');
        var highlightedIndex = -1;

        // Find currently highlighted suggestion
        for (var i = 0; i < suggestions.length; i++) {
            if (suggestions[i].classList.contains('highlighted')) {
                highlightedIndex = i;
                break;
            }
        }

        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (suggestionsContainer.style.display !== 'none') {
                    // Remove current highlight
                    if (highlightedIndex >= 0) {
                        suggestions[highlightedIndex].classList.remove('highlighted');
                    }
                    // Move to next suggestion
                    var nextIndex = highlightedIndex + 1;
                    if (nextIndex >= suggestions.length) nextIndex = 0;
                    if (suggestions[nextIndex]) {
                        suggestions[nextIndex].classList.add('highlighted');
                        suggestions[nextIndex].scrollIntoView({block: 'nearest'});
                    }
                }
                break;

            case 'ArrowUp':
                e.preventDefault();
                if (suggestionsContainer.style.display !== 'none') {
                    // Remove current highlight
                    if (highlightedIndex >= 0) {
                        suggestions[highlightedIndex].classList.remove('highlighted');
                    }
                    // Move to previous suggestion
                    var prevIndex = highlightedIndex - 1;
                    if (prevIndex < 0) prevIndex = suggestions.length - 1;
                    if (suggestions[prevIndex]) {
                        suggestions[prevIndex].classList.add('highlighted');
                        suggestions[prevIndex].scrollIntoView({block: 'nearest'});
                    }
                }
                break;

            case 'Enter':
                e.preventDefault();
                // Take the highlighted suggestion, or the first one if none is highlighted
                var chosen = suggestions[highlightedIndex >= 0 ? highlightedIndex : 0];
                if (chosen && suggestionsContainer.style.display !== 'none') {
                    selectSpecies(chosen.dataset.name);
                }
                break;

            case 'Escape':
                suggestionsContainer.style.display = 'none';
                break;
        }
    });

    // Click outside to hide suggestions
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !suggestionsContainer.contains(e.target)) {
            suggestionsContainer.style.display = 'none';
        }
    });

    // Also add mouseover for visual feedback
    suggestionsContainer.addEventListener('mouseover', function(e) {
        var item = e.target.closest('.suggestion-item');
        if (item) {
            // Remove all highlights
            suggestionsContainer.querySelectorAll('.suggestion-item').forEach(function(other) {
                other.classList.remove('highlighted');
            });
            // Add highlight to hovered item
            item.classList.add('highlighted');
        }
    });
}
