/* global Plotly */

(function () {
    const state = {
        loading: false,
        error: null,
        data: null,
        showCircles: true,
        sortColumn: "weighted_flux_ratio",
        sortDirection: "desc",
        selectedSourceId: null,
        plotClickBound: false,
    };

    const controls = {
        sourceId: document.getElementById("sourceId"),
        halfSizeArcmin: document.getElementById("halfSizeArcmin"),
        deltaMag: document.getElementById("deltaMag"),
        pixelScaleArcsec: document.getElementById("pixelScaleArcsec"),
        overlayRadiiPixels: document.getElementById("overlayRadiiPixels"),
        showCircles: document.getElementById("showCircles"),
        loadBtn: document.getElementById("loadBtn"),
        clearSelectionBtn: document.getElementById("clearSelectionBtn"),
    };

    const ui = {
        plot: document.getElementById("plot"),
        errorBox: document.getElementById("errorBox"),
        metaInfo: document.getElementById("metaInfo"),
        contaminantsBody: document.getElementById("contaminantsBody"),
        contaminantsTable: document.getElementById("contaminantsTable"),
        selectionNote: document.getElementById("selectionNote"),
    };

    function apiBaseUrl() {
        return (window.FIELD_STAR_MAP_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
    }

    function splitStars(stars) {
        return {
            variable: stars.filter((s) => s.is_variable),
            nonVariable: stars.filter((s) => !s.is_variable),
        };
    }

    function markerSize(fluxRatio) {
        const raw = 6 + 20 * Math.sqrt(Math.max(fluxRatio, 0));
        return Math.max(5, Math.min(raw, 34));
    }

    function isSelectedStar(sourceId) {
        return state.selectedSourceId === sourceId;
    }

    function markerSizeForStar(star) {
        const base = markerSize(star.flux_ratio);
        return isSelectedStar(star.source_id) ? base + 8 : base;
    }

    function markerLineWidthForStar(star) {
        return isSelectedStar(star.source_id) ? 2.5 : 0.6;
    }

    function formatFluxRatio(value) {
        return value.toLocaleString("it-IT", {
            useGrouping: false,
            minimumSignificantDigits: 2,
            maximumSignificantDigits: 2,
            notation: "standard",
        });
    }

    function formatWeightedFluxRatio(value) {
        if (!Number.isFinite(value)) {
            return "-";
        }
        if (value === 0) {
            return "0,000000";
        }

        const fixed = value.toLocaleString("it-IT", {
            useGrouping: false,
            minimumFractionDigits: 6,
            maximumFractionDigits: 6,
        });

        if (fixed === "0,000000" || fixed === "-0,000000") {
            return value.toExponential(2).replace(".", ",");
        }
        return fixed;
    }

    function escapeHtml(input) {
        return String(input)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function sortIndicator(column) {
        if (state.sortColumn !== column) {
            return "";
        }
        return state.sortDirection === "asc" ? " ^" : " v";
    }

    function sortTopContaminants(rows) {
        const sorted = [...rows];
        sorted.sort((a, b) => {
            let comparison = 0;
            switch (state.sortColumn) {
                case "source_id":
                    comparison = a.source_id.localeCompare(b.source_id);
                    break;
                case "var_type":
                    comparison = (a.var_type || "").localeCompare(b.var_type || "");
                    break;
                case "r_arcsec":
                case "r_arcmin":
                    comparison = a.r_arcsec - b.r_arcsec;
                    break;
                case "g_mag":
                    comparison = a.g_mag - b.g_mag;
                    break;
                case "delta_mag":
                    comparison = a.delta_mag - b.delta_mag;
                    break;
                case "flux_ratio":
                    comparison = a.flux_ratio - b.flux_ratio;
                    break;
                case "weighted_flux_ratio":
                    comparison = a.weighted_flux_ratio - b.weighted_flux_ratio;
                    break;
                case "period_days":
                    comparison = (a.period_days ?? Number.POSITIVE_INFINITY) - (b.period_days ?? Number.POSITIVE_INFINITY);
                    break;
                default:
                    comparison = 0;
            }
            if (comparison === 0) {
                comparison = a.source_id.localeCompare(b.source_id);
            }
            return state.sortDirection === "asc" ? comparison : -comparison;
        });
        return sorted;
    }

    function updateSortHeaderLabels() {
        const fallbackLabelBySortKey = {
            source_id: "src id",
            r_arcsec: "r sec",
            r_arcmin: "r min",
            g_mag: "G mag",
            delta_mag: "delta mag",
            flux_ratio: "flux r",
            weighted_flux_ratio: "PSF flux",
            period_days: "Per",
            var_type: "var",
        };
        const headers = ui.contaminantsTable.querySelectorAll("thead button[data-sort]");
        headers.forEach((btn) => {
            const sortKey = btn.getAttribute("data-sort");
            const baseLabel = btn.getAttribute("data-label") || fallbackLabelBySortKey[sortKey] || sortKey;
            btn.textContent = `${baseLabel}${sortIndicator(sortKey)}`;
        });
    }

    function renderError() {
        if (!state.error) {
            ui.errorBox.classList.add("hidden");
            ui.errorBox.textContent = "";
            return;
        }
        ui.errorBox.classList.remove("hidden");
        ui.errorBox.textContent = `Errore: ${state.error}`;
    }

    function buildShapes() {
        if (!state.data || !state.showCircles) {
            return [];
        }
        return state.data.params.overlay_radii_arcsec.map((radius) => ({
            type: "circle",
            xref: "x",
            yref: "y",
            x0: -radius,
            y0: -radius,
            x1: radius,
            y1: radius,
            line: { color: "#666", width: 1, dash: "dot" },
        }));
    }

    function renderPlot() {
        const stars = state.data?.stars || [];
        const grouped = splitStars(stars);
        const target = state.data?.target || null;

        const traces = [
            {
                type: "scattergl",
                mode: "markers",
                name: "Stelle non variabili",
                x: grouped.nonVariable.map((s) => s.x_arcsec),
                y: grouped.nonVariable.map((s) => s.y_arcsec),
                customdata: grouped.nonVariable.map((s) => s.source_id),
                marker: {
                    size: grouped.nonVariable.map(markerSizeForStar),
                    color: grouped.nonVariable.map((s) => (isSelectedStar(s.source_id) ? "#ffcc00" : "#2f6d9b")),
                    opacity: 0.82,
                    line: {
                        color: "#ffffff",
                        width: grouped.nonVariable.map(markerLineWidthForStar),
                    },
                },
                hovertemplate:
                    "source_id=%{customdata}<br>x=%{x:.2f} arcsec<br>y=%{y:.2f} arcsec<extra></extra>",
            },
            {
                type: "scattergl",
                mode: "markers",
                name: "Variabili note",
                x: grouped.variable.map((s) => s.x_arcsec),
                y: grouped.variable.map((s) => s.y_arcsec),
                customdata: grouped.variable.map((s) => s.source_id),
                marker: {
                    size: grouped.variable.map(markerSizeForStar),
                    color: grouped.variable.map((s) => (isSelectedStar(s.source_id) ? "#ffcc00" : "#d64545")),
                    opacity: 0.9,
                    line: {
                        color: "#ffffff",
                        width: grouped.variable.map(markerLineWidthForStar),
                    },
                },
                hovertemplate:
                    "source_id=%{customdata}<br>x=%{x:.2f} arcsec<br>y=%{y:.2f} arcsec<extra></extra>",
            },
        ];

        if (target) {
            traces.push({
                type: "scatter",
                mode: "markers",
                name: "Target",
                x: [0],
                y: [0],
                customdata: [target.source_id],
                marker: {
                    symbol: "star",
                    color: state.selectedSourceId === target.source_id ? "#f59e0b" : "#111111",
                    size: state.selectedSourceId === target.source_id ? 22 : 16,
                    line: {
                        width: state.selectedSourceId === target.source_id ? 2 : 0,
                        color: "#111111",
                    },
                },
                hovertemplate: `target=${target.source_id}<br>G=${target.g_mag.toFixed(3)}<extra></extra>`,
            });
        }

        const layout = {
            autosize: true,
            title: {
                text: "Field Star Map (offset TAN in arcsec)",
                x: 0.5,
                xanchor: "center",
                y: 0.98,
                yanchor: "top",
            },
            uirevision: state.data
                ? `${state.data.target.source_id}-${state.data.params.half_size_arcmin}-${state.data.params.delta_mag}-${state.data.params.pixel_scale_arcsec}`
                : "no-data",
            paper_bgcolor: "#ffffff",
            plot_bgcolor: "#ffffff",
            xaxis: {
                title: "x [arcsec] (Est +)",
                zeroline: true,
                showgrid: true,
                scaleanchor: "y",
                scaleratio: 1,
            },
            yaxis: {
                title: "y [arcsec] (Nord +)",
                zeroline: true,
                showgrid: true,
            },
            shapes: buildShapes(),
            margin: { l: 50, r: 20, t: 80, b: 45 },
            legend: { orientation: "h", x: 0, xanchor: "left", y: 1.03, yanchor: "bottom" },
        };

        Plotly.react(ui.plot, traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d"] });

        if (!state.plotClickBound && typeof ui.plot.on === "function") {
            ui.plot.on("plotly_click", (event) => {
                const point = event.points && event.points[0];
                if (!point || point.customdata == null) {
                    return;
                }
                const clickedId = String(point.customdata);
                state.selectedSourceId = state.selectedSourceId === clickedId ? null : clickedId;
                renderAll();

                if (state.selectedSourceId) {
                    const targetRow = document.getElementById(`row-${state.selectedSourceId}`);
                    if (targetRow) {
                        targetRow.scrollIntoView({ block: "nearest" });
                    }
                }
            });
            state.plotClickBound = true;
        }
    }

    function renderMeta(topContaminants) {
        const meta = state.data?.meta;
        if (!meta) {
            ui.metaInfo.textContent = "";
            return;
        }
        const parts = [
            `stars_cone_count: ${meta.stars_cone_count}`,
            `stars_square_count: ${meta.stars_square_count}`,
            `top_contaminants: ${topContaminants.length}`,
        ];
        if (meta.truncated) {
            parts.push("truncated: true");
        }
        ui.metaInfo.textContent = parts.join(" | ");
    }

    function renderSelectionNote(topContaminants) {
        if (!state.selectedSourceId) {
            ui.selectionNote.classList.add("hidden");
            ui.selectionNote.textContent = "";
            return;
        }
        const inTop = topContaminants.some((row) => row.source_id === state.selectedSourceId);
        if (inTop) {
            ui.selectionNote.classList.add("hidden");
            ui.selectionNote.textContent = "";
            return;
        }
        ui.selectionNote.classList.remove("hidden");
        ui.selectionNote.textContent = `Stella selezionata (${state.selectedSourceId}) non presente nella top list.`;
    }

    function renderTable() {
        const topContaminants = sortTopContaminants(state.data?.top_contaminants || []);

        ui.contaminantsBody.innerHTML = topContaminants
            .map((row) => {
                const selectedClass = row.source_id === state.selectedSourceId ? "selected" : "";
                return `<tr id="row-${escapeHtml(row.source_id)}" class="${selectedClass}" data-source-id="${escapeHtml(row.source_id)}">
                    <td>${escapeHtml(row.source_id)}</td>
                    <td>${row.r_arcsec.toFixed(2)}</td>
                    <td>${(row.r_arcsec / 60).toFixed(3)}</td>
                    <td>${row.g_mag.toFixed(3)}</td>
                    <td>${row.delta_mag.toFixed(3)}</td>
                    <td>${formatFluxRatio(row.flux_ratio)}</td>
                    <td>${formatWeightedFluxRatio(row.weighted_flux_ratio)}</td>
                    <td>${row.period_days == null ? "-" : row.period_days.toFixed(4)}</td>
                    <td>${escapeHtml(row.var_type || "-")}</td>
                </tr>`;
            })
            .join("");

        renderMeta(topContaminants);
        renderSelectionNote(topContaminants);
        updateSortHeaderLabels();
        controls.clearSelectionBtn.disabled = !state.selectedSourceId;
    }

    function renderAll() {
        renderError();
        renderPlot();
        renderTable();
    }

    async function loadData() {
        state.loading = true;
        state.error = null;
        controls.loadBtn.disabled = true;
        controls.loadBtn.textContent = "Loading...";
        renderError();

        try {
            const params = new URLSearchParams({
                source_id: controls.sourceId.value.trim(),
                half_size_arcmin: String(Number(controls.halfSizeArcmin.value)),
                delta_mag: String(Number(controls.deltaMag.value)),
                pixel_scale_arcsec: String(Number(controls.pixelScaleArcsec.value)),
                overlay_radii_pixels: controls.overlayRadiiPixels.value,
                max_results: "5000",
            });

            const response = await fetch(`${apiBaseUrl()}/field-star-map?${params.toString()}`);
            const data = await response.json();

            if (!response.ok) {
                const msg = data?.error || data?.detail || "Request failed";
                throw new Error(msg);
            }

            state.data = data;
            state.selectedSourceId = null;
            renderAll();
        } catch (err) {
            state.error = err instanceof Error ? err.message : "Unknown error";
            state.data = null;
            state.selectedSourceId = null;
            renderAll();
        } finally {
            state.loading = false;
            controls.loadBtn.disabled = false;
            controls.loadBtn.textContent = "Load";
        }
    }

    function toggleSort(column) {
        if (column === state.sortColumn) {
            state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
            state.sortColumn = column;
            state.sortDirection = column === "flux_ratio" || column === "weighted_flux_ratio" ? "desc" : "asc";
        }
        renderTable();
    }

    function attachEvents() {
        controls.loadBtn.addEventListener("click", loadData);

        controls.showCircles.addEventListener("change", () => {
            state.showCircles = controls.showCircles.checked;
            renderPlot();
        });

        controls.clearSelectionBtn.addEventListener("click", () => {
            state.selectedSourceId = null;
            renderAll();
        });

        ui.contaminantsTable.querySelectorAll("thead button[data-sort]").forEach((btn) => {
            btn.addEventListener("click", () => toggleSort(btn.getAttribute("data-sort")));
        });

        ui.contaminantsBody.addEventListener("click", (event) => {
            const row = event.target.closest("tr[data-source-id]");
            if (!row) {
                return;
            }
            const sourceId = row.getAttribute("data-source-id");
            state.selectedSourceId = state.selectedSourceId === sourceId ? null : sourceId;
            renderAll();
        });

    }

    function init() {
        attachEvents();
        renderAll();
        loadData();
    }

    init();
})();
