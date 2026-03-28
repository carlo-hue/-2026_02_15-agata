(function () {
    const appRoot = document.getElementById("tpfApp");
    const form = document.getElementById("tpfForm");
    const gaiaSourceIdInput = document.getElementById("gaiaSourceIdInput");
    const sectorInput = document.getElementById("sectorInput");
    const runButton = document.getElementById("runButton");
    const saveButton = document.getElementById("saveButton");
    const gaiaOverlayToggleButton = document.getElementById("gaiaOverlayToggleButton");
    const targetModeButton = document.getElementById("targetModeButton");
    const backgroundModeButton = document.getElementById("backgroundModeButton");
    const recalcButton = document.getElementById("recalcButton");
    const frameSlider = document.getElementById("frameSlider");
    const frameIndexLabel = document.getElementById("frameIndexLabel");
    const frameTimeLabel = document.getElementById("frameTimeLabel");
    const frameInfo = document.getElementById("frameInfo");
    const statusBox = document.getElementById("statusBox");
    const saveStatusBox = document.getElementById("saveStatusBox");
    const errorBox = document.getElementById("errorBox");
    const output = document.getElementById("output");
    const returnPayloadBox = document.getElementById("returnPayloadBox");
    const targetInfo = document.getElementById("targetInfo");
    const tpfInfo = document.getElementById("tpfInfo");
    const tpfHeaderMeta = document.getElementById("tpfHeaderMeta");
    const overlayInfo = document.getElementById("overlayInfo");
    const tpfDetailsInfo = document.getElementById("tpfDetailsInfo");
    const overlayDetailsInfo = document.getElementById("overlayDetailsInfo");
    const editInfo = document.getElementById("editInfo");
    const maskInfo = document.getElementById("maskInfo");
    const lightcurveInfo = document.getElementById("lightcurveInfo");
    const tpfPlot = document.getElementById("tpfPlot");
    const lightcurvePlot = document.getElementById("lightcurvePlot");

    let lastRunResult = null;
    let targetMask = [];
    let backgroundMask = [];
    let committedTargetMask = [];
    let committedBackgroundMask = [];
    let editMode = "target";
    let editingEnabled = false;
    let gaiaOverlayEnabled = true;
    let currentFrameIndex = 0;
    let tpfFrames = [];
    let tpfFrameTimes = [];
    let lightcurveFrameIndices = [];

    if (
        !appRoot || !form || !gaiaSourceIdInput || !sectorInput || !runButton || !saveButton
        || !gaiaOverlayToggleButton || !targetModeButton || !backgroundModeButton || !recalcButton
        || !frameSlider || !frameIndexLabel || !frameTimeLabel || !frameInfo
        || !statusBox || !saveStatusBox || !errorBox || !output || !returnPayloadBox || !targetInfo
        || !tpfInfo || !tpfHeaderMeta || !overlayInfo || !tpfDetailsInfo || !overlayDetailsInfo
        || !editInfo || !maskInfo || !lightcurveInfo || !tpfPlot || !lightcurvePlot
    ) {
        return;
    }

    const endpointUrls = {
        runUrl: appRoot.dataset.runUrl || "/tpf/api/run",
        saveUrl: appRoot.dataset.saveUrl || "/tpf/api/save",
    };

    const pageContext = {
        mode: appRoot.dataset.mode || "standalone",
        gaia_source_id: appRoot.dataset.gaiaSourceId || "",
        sector: appRoot.dataset.sector || "",
        source_context: appRoot.dataset.sourceContext || null,
    };

    function setStatus(message, tone) {
        statusBox.textContent = message || "-";
        statusBox.className = `status-box ${tone || "status-neutral"}`;
    }

    function setSaveStatus(message, tone) {
        saveStatusBox.textContent = message || "-";
        saveStatusBox.className = `status-box ${tone || "status-neutral"}`;
    }

    function setError(message) {
        if (!message) {
            errorBox.textContent = "";
            errorBox.classList.add("hidden");
            return;
        }
        errorBox.textContent = message;
        errorBox.classList.remove("hidden");
    }

    function setButtonBusy(button, busyText, isBusy) {
        if (!button.dataset.originalText) {
            button.dataset.originalText = button.textContent;
        }
        button.textContent = isBusy ? busyText : button.dataset.originalText;
        button.disabled = isBusy;
    }

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function cloneMask(maskMatrix) {
        if (!Array.isArray(maskMatrix)) {
            return [];
        }
        return maskMatrix.map((row) => Array.isArray(row) ? row.map((value) => !!value) : []);
    }

    function masksEqual(leftMask, rightMask) {
        if (!Array.isArray(leftMask) || !Array.isArray(rightMask) || leftMask.length !== rightMask.length) {
            return false;
        }
        for (let row = 0; row < leftMask.length; row += 1) {
            if (!Array.isArray(leftMask[row]) || !Array.isArray(rightMask[row]) || leftMask[row].length !== rightMask[row].length) {
                return false;
            }
            for (let col = 0; col < leftMask[row].length; col += 1) {
                if (!!leftMask[row][col] !== !!rightMask[row][col]) {
                    return false;
                }
            }
        }
        return true;
    }

    function masksNeedRecalc() {
        if (!editingEnabled) {
            return false;
        }
        return !masksEqual(targetMask, committedTargetMask) || !masksEqual(backgroundMask, committedBackgroundMask);
    }

    function maskSummary(currentTargetMask, currentBackgroundMask) {
        let targetPixels = 0;
        let backgroundPixels = 0;
        for (let row = 0; row < currentTargetMask.length; row += 1) {
            for (let col = 0; col < currentTargetMask[row].length; col += 1) {
                if (currentTargetMask[row][col]) targetPixels += 1;
                if (currentBackgroundMask[row] && currentBackgroundMask[row][col]) backgroundPixels += 1;
            }
        }
        return { targetPixels, backgroundPixels };
    }

    function buildCurrentMasksPayload(mode, message) {
        const summary = maskSummary(targetMask, backgroundMask);
        return {
            available: editingEnabled,
            mode: mode || "manual-ui",
            message: message || 'Premi "Ricalcola light curve" per aggiornare la curva.',
            target: cloneMask(targetMask),
            background: cloneMask(backgroundMask),
            summary: {
                target_pixels: summary.targetPixels,
                background_pixels: summary.backgroundPixels,
            },
        };
    }

    function clearPlots() {
        Plotly.purge(tpfPlot);
        Plotly.purge(lightcurvePlot);
        tpfPlot.__maskClickBound = false;
        lightcurvePlot.__lightcurveClickBound = false;
        tpfPlot.innerHTML = "";
        lightcurvePlot.innerHTML = "";
    }

    function resetFrameState() {
        currentFrameIndex = 0;
        tpfFrames = [];
        tpfFrameTimes = [];
        lightcurveFrameIndices = [];
        frameSlider.min = "0";
        frameSlider.max = "0";
        frameSlider.step = "1";
        frameSlider.value = "0";
        frameSlider.disabled = true;
        frameIndexLabel.textContent = "Frame: - / -";
        frameTimeLabel.textContent = "Time: -";
        frameInfo.textContent = "Navigazione frame disponibile solo con TPF reale.";
    }

    function resetSections() {
        renderTarget(null);
        tpfHeaderMeta.textContent = "gaia_source_id=- | sector=- | ra=- | dec=- | gmag=-";
        tpfInfo.textContent = "TPF non ancora richiesto.";
        overlayInfo.textContent = "Overlay target/Gaia non ancora disponibile.";
        tpfDetailsInfo.textContent = "TPF non ancora richiesto.";
        overlayDetailsInfo.textContent = "Overlay target/Gaia non ancora disponibile.";
        maskInfo.textContent = "Selezione automatica foreground/background non ancora disponibile.";
        maskInfo.classList.remove("warning");
        lightcurveInfo.textContent = "Light curve non ancora richiesta.";
        editInfo.textContent = "Editing pixel disponibile solo con TPF reale.";
        resetFrameState();
    }

    function renderTarget(target) {
        if (!target) {
            targetInfo.className = "info-grid empty-state";
            targetInfo.textContent = "Nessun target caricato.";
            return;
        }
        targetInfo.className = "info-grid";
        targetInfo.innerHTML = `
            <div><span class="k">Gaia source_id</span><span class="v mono">${escapeHtml(target.gaia_source_id || "-")}</span></div>
            <div><span class="k">Catalogo</span><span class="v">${escapeHtml(target.catalog || "Gaia DR3")}</span></div>
            <div><span class="k">RA [deg]</span><span class="v mono">${escapeHtml(target.ra_deg ?? "-")}</span></div>
            <div><span class="k">Dec [deg]</span><span class="v mono">${escapeHtml(target.dec_deg ?? "-")}</span></div>
            <div><span class="k">Gmag</span><span class="v">${escapeHtml(target.gmag ?? "-")}</span></div>
        `;
    }

    function getFrameCount() {
        return Array.isArray(tpfFrames) ? tpfFrames.length : 0;
    }

    function clampFrameIndex(index) {
        const count = getFrameCount();
        if (count <= 0) {
            return 0;
        }
        const numeric = Number.isFinite(index) ? index : parseInt(index, 10);
        if (!Number.isFinite(numeric)) {
            return 0;
        }
        return Math.min(count - 1, Math.max(0, Math.round(numeric)));
    }

    function getCurrentFrameGrid(tpf) {
        if (tpf && tpf.frames && tpf.frames.available && getFrameCount() > 0) {
            return tpfFrames[clampFrameIndex(currentFrameIndex)];
        }
        return tpf && Array.isArray(tpf.flux_grid) ? tpf.flux_grid : null;
    }

    function findLightcurvePointIndexForFrame(frameIndex) {
        if (Array.isArray(lightcurveFrameIndices) && lightcurveFrameIndices.length) {
            const directIndex = lightcurveFrameIndices.indexOf(frameIndex);
            if (directIndex >= 0) {
                return directIndex;
            }
            return -1;
        }

        if (lastRunResult && lastRunResult.lightcurve && Array.isArray(lastRunResult.lightcurve.time)) {
            return frameIndex < lastRunResult.lightcurve.time.length ? frameIndex : -1;
        }
        return -1;
    }

    function updateFrameControls(tpf) {
        const frames = tpf && tpf.frames ? tpf.frames : null;
        if (!frames || !frames.available || getFrameCount() === 0) {
            frameSlider.disabled = true;
            frameIndexLabel.textContent = "Frame: - / -";
            frameTimeLabel.textContent = "Time: -";
            frameInfo.textContent = (frames && frames.message) || "Navigazione frame disponibile solo con TPF reale.";
            return;
        }

        const safeIndex = clampFrameIndex(currentFrameIndex);
        currentFrameIndex = safeIndex;
        const count = getFrameCount();
        const currentTime = Array.isArray(tpfFrameTimes) && tpfFrameTimes[safeIndex] !== undefined
            ? tpfFrameTimes[safeIndex]
            : "-";

        frameSlider.disabled = false;
        frameSlider.min = "0";
        frameSlider.max = String(Math.max(0, count - 1));
        frameSlider.step = "1";
        frameSlider.value = String(safeIndex);
        frameIndexLabel.textContent = `Frame: ${safeIndex + 1} / ${count}`;
        frameTimeLabel.textContent = `Time: ${currentTime}`;
        frameInfo.textContent = `Frame reale corrente: ${safeIndex + 1}/${count} | Time=${currentTime} | ${frames.message || "Clicca un punto della light curve per vedere il frame corrispondente."}`;
    }
    function handleTpfPlotClick(eventData) {
        if (!editingEnabled || !lastRunResult || !lastRunResult.tpf || lastRunResult.tpf.mode !== "real") {
            return;
        }
        const point = eventData && eventData.points && eventData.points[0] ? eventData.points[0] : null;
        if (!point || typeof point.x !== "number" || typeof point.y !== "number") {
            return;
        }
        if (point.data && point.data.type && point.data.type !== "heatmap") {
            return;
        }

        const row = Math.round(point.y);
        const col = Math.round(point.x);
        if (!targetMask[row] || targetMask[row][col] === undefined || !backgroundMask[row] || backgroundMask[row][col] === undefined) {
            return;
        }

        if (editMode === "target") {
            const nextValue = !targetMask[row][col];
            targetMask[row][col] = nextValue;
            if (nextValue) {
                backgroundMask[row][col] = false;
            }
        } else {
            const nextValue = !backgroundMask[row][col];
            backgroundMask[row][col] = nextValue;
            if (nextValue) {
                targetMask[row][col] = false;
            }
        }

        renderCurrentTpfState();
        editInfo.textContent = `Modalita' editing attiva: ${editMode}. Clicca un pixel del TPF per modificarlo e poi premi "Ricalcola light curve".`;
    }

    function buildMaskShapes(maskMatrix, kind) {
        if (!Array.isArray(maskMatrix) || !maskMatrix.length) {
            return [];
        }

        const shapes = [];
        for (let row = 0; row < maskMatrix.length; row += 1) {
            for (let col = 0; col < maskMatrix[row].length; col += 1) {
                if (!maskMatrix[row][col]) {
                    continue;
                }

                const x0 = col - 0.5;
                const x1 = col + 0.5;
                const y0 = row - 0.5;
                const y1 = row + 0.5;

                if (kind === "target") {
                    shapes.push({
                        type: "rect",
                        xref: "x",
                        yref: "y",
                        x0,
                        x1,
                        y0,
                        y1,
                        line: {
                            color: "rgba(255, 0, 0, 0.98)",
                            width: 2.5,
                        },
                        fillcolor: "rgba(255, 0, 0, 0.10)",
                    });
                } else if (kind === "background") {
                    shapes.push({
                        type: "rect",
                        xref: "x",
                        yref: "y",
                        x0,
                        x1,
                        y0,
                        y1,
                        line: {
                            color: "rgba(255, 255, 255, 0.95)",
                            width: 1.4,
                        },
                        fillcolor: "rgba(255, 255, 255, 0.02)",
                    });
                }
            }
        }

        return shapes;
    }

    function buildTargetOverlayTrace(overlay) {
        if (!overlay || !overlay.target_position || overlay.target_position.x === undefined || overlay.target_position.y === undefined) {
            return null;
        }
        return {
            x: [overlay.target_position.x],
            y: [overlay.target_position.y],
            type: "scatter",
            mode: "markers",
            name: "Target",
            marker: {
                symbol: "x",
                size: 14,
                color: "#facc15",
                line: {
                    color: "#facc15",
                    width: 2,
                },
            },
            hovertemplate: "Target<br>x=%{x:.2f}<br>y=%{y:.2f}<extra></extra>",
        };
    }

    function buildGaiaOverlayTrace(overlay) {
        if (!gaiaOverlayEnabled || !overlay || !Array.isArray(overlay.gaia_sources) || !overlay.gaia_sources.length) {
            return null;
        }
        return {
            x: overlay.gaia_sources.map((item) => item.x),
            y: overlay.gaia_sources.map((item) => item.y),
            text: overlay.gaia_sources.map((item) => `source_id=${item.source_id}<br>Gmag=${item.gmag ?? "-"}`),
            type: "scatter",
            mode: "markers",
            name: "Gaia",
            marker: {
                symbol: "circle",
                size: 5,
                color: "rgba(37, 99, 235, 0.78)",
                line: {
                    color: "rgba(219, 234, 254, 0.75)",
                    width: 0.8,
                },
            },
            hovertemplate: "%{text}<br>x=%{x:.2f}<br>y=%{y:.2f}<extra></extra>",
        };
    }

    function updateGaiaOverlayToggleButton() {
        gaiaOverlayToggleButton.textContent = gaiaOverlayEnabled ? "Gaia overlay ON" : "Gaia overlay OFF";
        gaiaOverlayToggleButton.classList.toggle("is-off", !gaiaOverlayEnabled);
        gaiaOverlayToggleButton.title = gaiaOverlayEnabled
            ? "Nasconde le sorgenti Gaia per facilitare la selezione dei pixel."
            : "Mostra di nuovo le sorgenti Gaia sul TPF.";
    }

    function renderTPF(grid, masks) {
        tpfPlot.__maskClickBound = false;
        const traces = [{
            z: grid,
            type: "heatmap",
            colorscale: "Viridis",
            hoverongaps: false,
            showscale: true,
            name: "TPF",
        }];
        const shapes = [];
        const currentTpf = buildCurrentTpfView();
        const overlay = currentTpf && currentTpf.overlay ? currentTpf.overlay : null;
        const gaiaTrace = buildGaiaOverlayTrace(overlay);
        const targetTrace = buildTargetOverlayTrace(overlay);

        if (gaiaTrace) {
            traces.push(gaiaTrace);
        }
        if (targetTrace) {
            traces.push(targetTrace);
        }

        if (masks && masks.available) {
            shapes.push(...buildMaskShapes(masks.background, "background"));
            shapes.push(...buildMaskShapes(masks.target, "target"));
            traces.push({
                x: [null],
                y: [null],
                type: "scatter",
                mode: "markers",
                name: "Background",
                marker: {
                    symbol: "square",
                    size: 12,
                    color: "rgba(255,255,255,0.20)",
                    line: {
                        color: "rgba(255,255,255,0.95)",
                        width: 1.5,
                    },
                },
                hoverinfo: "skip",
            });
            traces.push({
                x: [null],
                y: [null],
                type: "scatter",
                mode: "markers",
                name: "Foreground",
                marker: {
                    symbol: "square",
                    size: 12,
                    color: "rgba(255,0,0,0.16)",
                    line: {
                        color: "rgba(255,0,0,0.98)",
                        width: 2.5,
                    },
                },
                hoverinfo: "skip",
            });
        }

        const layout = {
            title: getFrameCount() > 0 ? `TPF Flux Grid | frame ${clampFrameIndex(currentFrameIndex) + 1}` : "TPF Flux Grid",
            margin: { t: 40, r: 20, b: 40, l: 40 },
            xaxis: { title: "Pixel X", constrain: "domain" },
            yaxis: { title: "Pixel Y", autorange: "reversed", scaleanchor: "x", scaleratio: 1 },
            legend: { orientation: "h" },
            shapes,
        };
        Plotly.newPlot(tpfPlot, traces, layout, { responsive: true, displayModeBar: false }).then(function () {
            if (!tpfPlot.__maskClickBound && typeof tpfPlot.on === "function") {
                tpfPlot.on("plotly_click", handleTpfPlotClick);
                tpfPlot.__maskClickBound = true;
            }
        });
    }

    function handleLightcurveClick(eventData) {
        const point = eventData && eventData.points && eventData.points[0] ? eventData.points[0] : null;
        if (!point || typeof point.pointIndex !== "number") {
            return;
        }
        const clickedIndex = point.pointIndex;
        const targetFrameIndex = Array.isArray(lightcurveFrameIndices) && lightcurveFrameIndices.length
            ? lightcurveFrameIndices[clickedIndex]
            : clickedIndex;
        setCurrentFrameIndex(targetFrameIndex);
    }

    function renderLightcurve(lightcurve) {
        lightcurvePlot.__lightcurveClickBound = false;
        const time = Array.isArray(lightcurve.time) ? lightcurve.time : [];
        const corrected = Array.isArray(lightcurve.corrected_flux) ? lightcurve.corrected_flux : (Array.isArray(lightcurve.flux) ? lightcurve.flux : []);
        const traces = [{
            x: time,
            y: corrected,
            mode: "lines",
            name: "Corrected Flux",
            line: { color: "#2f7ed8", width: 2 },
        }];

        const highlightIndex = findLightcurvePointIndexForFrame(clampFrameIndex(currentFrameIndex));
        if (highlightIndex >= 0 && highlightIndex < time.length && highlightIndex < corrected.length) {
            traces.push({
                x: [time[highlightIndex]],
                y: [corrected[highlightIndex]],
                mode: "markers",
                name: "Frame corrente",
                marker: {
                    size: 9,
                    color: "#ef4444",
                    line: {
                        color: "#ffffff",
                        width: 1.5,
                    },
                },
                hovertemplate: "Frame corrente<br>time=%{x}<br>flux=%{y}<extra></extra>",
            });
        }

        const layout = {
            title: "Light Curve Corretta",
            margin: { t: 40, r: 20, b: 40, l: 50 },
            xaxis: { title: "Time" },
            yaxis: { title: "Corrected Flux" },
        };
        Plotly.newPlot(lightcurvePlot, traces, layout, { responsive: true, displayModeBar: false }).then(function () {
            if (!lightcurvePlot.__lightcurveClickBound && typeof lightcurvePlot.on === "function") {
                lightcurvePlot.on("plotly_click", handleLightcurveClick);
                lightcurvePlot.__lightcurveClickBound = true;
            }
        });
    }
    function formatTpfInfo(tpf) {
        if (!tpf) {
            return "TPF non disponibile.";
        }
        const parts = [];
        if (tpf.message) parts.push(tpf.message);
        if (tpf.mode) parts.push(`mode=${tpf.mode}`);
        if (tpf.source && tpf.source.type) parts.push(`source=${tpf.source.type}`);
        if (Array.isArray(tpf.shape)) parts.push(`shape=${tpf.shape.join("x")}`);
        if (tpf.metadata && tpf.metadata.sector !== undefined && tpf.metadata.sector !== null) parts.push(`sector=${tpf.metadata.sector}`);
        if (tpf.metadata && tpf.metadata.camera !== undefined && tpf.metadata.camera !== null) parts.push(`camera=${tpf.metadata.camera}`);
        if (tpf.metadata && tpf.metadata.ccd !== undefined && tpf.metadata.ccd !== null) parts.push(`ccd=${tpf.metadata.ccd}`);
        if (tpf.metadata && tpf.metadata.tessmag !== undefined && tpf.metadata.tessmag !== null) parts.push(`tessmag=${tpf.metadata.tessmag}`);
        if (tpf.metadata && tpf.metadata.ticid !== undefined && tpf.metadata.ticid !== null) parts.push(`ticid=${tpf.metadata.ticid}`);
        return parts.join(" | ") || "TPF disponibile.";
    }

    function formatTpfHeaderMeta(result) {
        const input = result && result.input ? result.input : {};
        const target = result && result.target ? result.target : {};
        const gaiaSourceId = target.gaia_source_id || input.gaia_source_id || "-";
        const sector = input.sector ?? "-";
        const raDeg = target.ra_deg ?? "-";
        const decDeg = target.dec_deg ?? "-";
        const gmag = target.gmag ?? "-";
        return `gaia_source_id=${gaiaSourceId} | sector=${sector} | ra=${raDeg} | dec=${decDeg} | gmag=${gmag}`;
    }

    function formatMaskInfo(tpf) {
        if (!tpf || !tpf.masks) {
            return "Selezione foreground/background non disponibile.";
        }
        if (!tpf.masks.available) {
            return tpf.masks.message || "Selezione foreground/background non disponibile.";
        }
        const summary = tpf.masks.summary || {};
        return `${tpf.masks.message || "Maschere disponibili."} | target_pixels=${summary.target_pixels ?? 0} | background_pixels=${summary.background_pixels ?? 0}`;
    }

    function formatOverlayInfo(tpf) {
        if (!tpf || !tpf.overlay) {
            return "Overlay target/Gaia non disponibile.";
        }
        const parts = [];
        if (tpf.overlay.message) parts.push(tpf.overlay.message);
        if (tpf.overlay.target_position && tpf.overlay.target_position.source) parts.push(`target_source=${tpf.overlay.target_position.source}`);
        if (Array.isArray(tpf.overlay.gaia_sources)) parts.push(`gaia_sources=${tpf.overlay.gaia_sources.length}`);
        parts.push(`gaia_overlay=${gaiaOverlayEnabled ? "on" : "off"}`);
        parts.push("target=giallo");
        parts.push("gaia=blu");
        return parts.join(" | ");
    }

    function formatLightcurveInfo(lightcurve) {
        if (!lightcurve) {
            return "Light curve non disponibile.";
        }
        const parts = [];
        if (lightcurve.message) parts.push(lightcurve.message);
        if (lightcurve.mode) parts.push(`mode=${lightcurve.mode}`);
        if (lightcurve.summary && lightcurve.summary.target_pixels !== undefined) parts.push(`target_pixels=${lightcurve.summary.target_pixels}`);
        if (lightcurve.summary && lightcurve.summary.background_pixels !== undefined) parts.push(`background_pixels=${lightcurve.summary.background_pixels}`);
        return parts.join(" | ") || "Light curve disponibile.";
    }

    function setEditMode(mode) {
        editMode = mode === "background" ? "background" : "target";
        targetModeButton.classList.toggle("is-active", editMode === "target");
        backgroundModeButton.classList.toggle("is-active", editMode === "background");
        if (editingEnabled) {
            editInfo.textContent = `Modalita' editing attiva: ${editMode}. Clicca un pixel del TPF per modificarlo e poi premi "Ricalcola light curve".`;
        }
    }

    function updateEditingControls() {
        targetModeButton.disabled = !editingEnabled;
        backgroundModeButton.disabled = !editingEnabled;
        recalcButton.disabled = !editingEnabled;
        if (!editingEnabled) {
            const reason = lastRunResult && lastRunResult.tpf && lastRunResult.tpf.mode === "preview"
                ? "Editing pixel non disponibile: il TPF corrente e' una preview sintetica. Per abilitare Target, Background e Ricalcola light curve serve un TPF reale locale."
                : "Editing pixel disponibile solo con TPF reale.";
            editInfo.textContent = reason;
            targetModeButton.title = reason;
            backgroundModeButton.title = reason;
            recalcButton.title = reason;
        } else {
            editInfo.textContent = `Modalita' editing attiva: ${editMode}. Clicca un pixel del TPF per modificarlo e poi premi "Ricalcola light curve".`;
            targetModeButton.title = "Modalita' editing target attiva.";
            backgroundModeButton.title = "Modalita' editing background attiva.";
            recalcButton.title = "Ricalcola la light curve usando le maschere correnti.";
        }
        setEditMode(editMode);
    }

    function syncMasksFromResult(result) {
        const tpf = result && result.tpf ? result.tpf : null;
        if (tpf && tpf.mode === "real" && tpf.masks && tpf.masks.available) {
            targetMask = cloneMask(tpf.masks.target);
            backgroundMask = cloneMask(tpf.masks.background);
            committedTargetMask = cloneMask(tpf.masks.target);
            committedBackgroundMask = cloneMask(tpf.masks.background);
            editingEnabled = true;
        } else {
            targetMask = [];
            backgroundMask = [];
            committedTargetMask = [];
            committedBackgroundMask = [];
            editingEnabled = false;
        }
        updateEditingControls();
    }

    function syncFrameStateFromResult(result) {
        const tpf = result && result.tpf ? result.tpf : null;
        const frames = tpf && tpf.frames ? tpf.frames : null;
        if (frames && frames.available && Array.isArray(frames.grids) && frames.grids.length) {
            tpfFrames = frames.grids;
            tpfFrameTimes = Array.isArray(frames.time) ? frames.time : [];
            currentFrameIndex = clampFrameIndex(frames.initial_index || 0);
        } else {
            tpfFrames = [];
            tpfFrameTimes = [];
            currentFrameIndex = 0;
        }

        if (result && result.lightcurve && Array.isArray(result.lightcurve.frame_indices)) {
            lightcurveFrameIndices = result.lightcurve.frame_indices.slice();
        } else {
            lightcurveFrameIndices = [];
        }
    }

    function buildCurrentTpfView() {
        if (!lastRunResult || !lastRunResult.tpf) {
            return null;
        }
        if (!editingEnabled) {
            return lastRunResult.tpf;
        }
        return {
            ...lastRunResult.tpf,
            masks: buildCurrentMasksPayload("manual-ui", 'Premi "Ricalcola light curve" per aggiornare la curva.'),
        };
    }

    function renderCurrentTpfState() {
        const tpf = buildCurrentTpfView();
        if (!tpf) {
            return;
        }

        updateGaiaOverlayToggleButton();
        tpfHeaderMeta.textContent = formatTpfHeaderMeta(lastRunResult);
        tpfInfo.textContent = formatTpfInfo(tpf);
        overlayInfo.textContent = formatOverlayInfo(tpf);
        tpfDetailsInfo.textContent = tpfInfo.textContent;
        overlayDetailsInfo.textContent = overlayInfo.textContent;
        maskInfo.textContent = formatMaskInfo(tpf);
        maskInfo.classList.toggle("warning", masksNeedRecalc());
        updateFrameControls(tpf);

        const currentGrid = getCurrentFrameGrid(tpf);
        if (Array.isArray(currentGrid)) {
            renderTPF(currentGrid, tpf.masks || null);
        } else {
            Plotly.purge(tpfPlot);
            tpfPlot.innerHTML = "";
        }
    }

    function updateSections(data) {
        renderTarget(data.target || null);
        if (data.tpf && data.tpf.available && (Array.isArray(data.tpf.flux_grid) || (data.tpf.frames && data.tpf.frames.available))) {
            renderCurrentTpfState();
        } else {
            tpfHeaderMeta.textContent = formatTpfHeaderMeta(data);
            tpfInfo.textContent = formatTpfInfo(data.tpf);
            overlayInfo.textContent = formatOverlayInfo(data.tpf);
            tpfDetailsInfo.textContent = tpfInfo.textContent;
            overlayDetailsInfo.textContent = overlayInfo.textContent;
            maskInfo.textContent = formatMaskInfo(data.tpf);
            maskInfo.classList.toggle("warning", masksNeedRecalc());
            updateFrameControls(data.tpf || null);
            Plotly.purge(tpfPlot);
            tpfPlot.innerHTML = "";
        }

        if (data.lightcurve && data.lightcurve.available && Array.isArray(data.lightcurve.time) && Array.isArray(data.lightcurve.corrected_flux || data.lightcurve.flux)) {
            lightcurveInfo.textContent = formatLightcurveInfo(data.lightcurve);
            renderLightcurve(data.lightcurve);
        } else {
            lightcurveInfo.textContent = formatLightcurveInfo(data.lightcurve);
            Plotly.purge(lightcurvePlot);
            lightcurvePlot.innerHTML = "";
        }
    }

    function buildAgataReturnPayload(result, context) {
        const gaiaSourceId = result && result.input && result.input.gaia_source_id
            ? result.input.gaia_source_id
            : (context.gaia_source_id || null);
        const sector = result && result.input && result.input.sector !== undefined
            ? result.input.sector
            : (context.sector || null);

        return {
            component: "tpf",
            mode: context.mode,
            source_context: context.source_context || null,
            input: {
                gaia_source_id: gaiaSourceId,
                sector: sector,
            },
            result: {
                status: result && result.status ? result.status : "not-ready",
                target: result && result.target ? {
                    gaia_source_id: result.target.gaia_source_id || null,
                    catalog: result.target.catalog || null,
                    ra_deg: result.target.ra_deg ?? null,
                    dec_deg: result.target.dec_deg ?? null,
                    gmag: result.target.gmag ?? null,
                } : null,
                tpf: {
                    available: !!(result && result.tpf && result.tpf.available),
                    mode: result && result.tpf ? (result.tpf.mode || null) : null,
                    metadata: result && result.tpf && result.tpf.metadata ? {
                        sector: result.tpf.metadata.sector ?? null,
                        camera: result.tpf.metadata.camera ?? null,
                        ccd: result.tpf.metadata.ccd ?? null,
                        tessmag: result.tpf.metadata.tessmag ?? null,
                        ticid: result.tpf.metadata.ticid ?? null,
                    } : null,
                    frames: result && result.tpf && result.tpf.frames ? {
                        available: !!result.tpf.frames.available,
                        count: result.tpf.frames.count ?? 0,
                        current_index: getFrameCount() > 0 ? clampFrameIndex(currentFrameIndex) : null,
                    } : null,
                    overlay: result && result.tpf && result.tpf.overlay ? {
                        target_position: result.tpf.overlay.target_position || null,
                        gaia_sources_count: Array.isArray(result.tpf.overlay.gaia_sources) ? result.tpf.overlay.gaia_sources.length : 0,
                    } : null,
                    masks: result && result.tpf && result.tpf.masks ? {
                        available: !!result.tpf.masks.available,
                        mode: result.tpf.masks.mode || null,
                        summary: result.tpf.masks.summary || null,
                    } : null,
                },
                lightcurve: {
                    available: !!(result && result.lightcurve && result.lightcurve.available),
                    mode: result && result.lightcurve ? (result.lightcurve.mode || null) : null,
                    summary: result && result.lightcurve ? (result.lightcurve.summary || null) : null,
                },
                save: {
                    mode: result && result.save ? (result.save.mode || null) : null,
                    saved: !!(result && result.save && result.save.saved),
                },
            },
        };
    }

    function renderReturnPayloadPreview(result) {
        returnPayloadBox.textContent = JSON.stringify(buildAgataReturnPayload(result, pageContext), null, 2);
    }

    async function runPipeline(gaiaSourceId, sector, masks) {
        const response = await fetch(endpointUrls.runUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                gaia_source_id: gaiaSourceId,
                sector: sector,
                source_context: pageContext.source_context,
                masks: masks || undefined,
            }),
        });
        const data = await response.json().catch(() => ({ status: "error", message: "Risposta JSON non valida" }));
        output.textContent = JSON.stringify(data, null, 2);
        return { response, data };
    }

    async function handlePipelineSuccess(data, statusMessage) {
        lastRunResult = data;
        saveButton.disabled = false;
        syncMasksFromResult(data);
        syncFrameStateFromResult(data);
        const tpfAvailable = !!(data.tpf && data.tpf.available);
        const lcAvailable = !!(data.lightcurve && data.lightcurve.available);
        setStatus(
            statusMessage || data.message || `Pipeline completata | TPF: ${tpfAvailable ? "disponibile" : "non disponibile"} | Light curve: ${lcAvailable ? "disponibile" : "non disponibile"}`,
            "status-success"
        );
        setSaveStatus("Risultato pronto per un salvataggio stub.", "status-neutral");
        renderReturnPayloadPreview(lastRunResult);
        updateSections(data);
    }

    async function saveCurrentResult() {
        if (!lastRunResult) {
            setSaveStatus("Nessun risultato disponibile da salvare.", "status-error");
            return;
        }

        setButtonBusy(saveButton, "Salvataggio...", true);
        setSaveStatus("Salvataggio stub in corso...", "status-neutral");
        try {
            const payloadToSave = {
                ...lastRunResult,
                agata_context: pageContext,
            };
            const response = await fetch(endpointUrls.saveUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payloadToSave),
            });
            const data = await response.json().catch(() => ({ status: "error", message: "Risposta JSON non valida" }));
            output.textContent = JSON.stringify(data, null, 2);

            if (!response.ok || data.status === "error") {
                setSaveStatus(data.message || `Errore HTTP ${response.status}`, "status-error");
                return;
            }

            lastRunResult = {
                ...lastRunResult,
                save: {
                    mode: data.mode,
                    saved: data.saved,
                    save_id: data.save_id,
                    saved_at_utc: data.saved_at_utc,
                    summary: data.summary || null,
                },
            };
            renderReturnPayloadPreview(lastRunResult);
            const suffix = data.mode === "stub" ? " (stub)" : "";
            const savedAt = data.saved_at_utc ? ` | ${data.saved_at_utc}` : "";
            setSaveStatus(`${data.message || "Salvataggio completato."}${suffix}${savedAt}`, "status-success");
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            setSaveStatus(`Errore di rete durante il salvataggio: ${message}`, "status-error");
        } finally {
            setButtonBusy(saveButton, "Salvataggio...", false);
            saveButton.disabled = !lastRunResult;
        }
    }
    function setCurrentFrameIndex(nextIndex) {
        const clampedIndex = clampFrameIndex(nextIndex);
        currentFrameIndex = clampedIndex;
        if (!lastRunResult) {
            updateFrameControls(null);
            return;
        }
        renderCurrentTpfState();
        if (lastRunResult.lightcurve && lastRunResult.lightcurve.available) {
            renderLightcurve(lastRunResult.lightcurve);
        }
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const gaiaSourceId = String(gaiaSourceIdInput.value || "").trim();
        const sector = String(sectorInput.value || "").trim();
        pageContext.gaia_source_id = gaiaSourceId;
        pageContext.sector = sector;
        setError("");
        setStatus("Loading... esecuzione pipeline in corso.", "status-neutral");
        setSaveStatus("Nessun salvataggio eseguito.", "status-neutral");
        output.textContent = JSON.stringify({ status: "ok", message: "Loading..." }, null, 2);
        lastRunResult = null;
        targetMask = [];
        backgroundMask = [];
        committedTargetMask = [];
        committedBackgroundMask = [];
        editingEnabled = false;
        saveButton.disabled = true;
        updateEditingControls();
        resetFrameState();
        setButtonBusy(runButton, "Loading...", true);
        clearPlots();
        resetSections();
        renderReturnPayloadPreview(null);

        try {
            const { response, data } = await runPipeline(gaiaSourceId, sector, null);
            if (!response.ok || data.status === "error") {
                lastRunResult = null;
                saveButton.disabled = true;
                setStatus(data.message || "Pipeline completata con errore.", "status-error");
                setError(data.message || `Errore HTTP ${response.status}`);
                renderReturnPayloadPreview(null);
                updateSections(data || {});
                return;
            }
            await handlePipelineSuccess(data, null);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            lastRunResult = null;
            saveButton.disabled = true;
            setStatus("Errore di rete durante la pipeline.", "status-error");
            setError(message);
            output.textContent = JSON.stringify({ status: "error", message }, null, 2);
            clearPlots();
            resetSections();
            renderReturnPayloadPreview(null);
        } finally {
            setButtonBusy(runButton, "Loading...", false);
        }
    });

    recalcButton.addEventListener("click", async function () {
        if (!editingEnabled || !lastRunResult) {
            return;
        }
        setError("");
        setButtonBusy(recalcButton, "Ricalcolo...", true);
        setStatus("Ricalcolo light curve in corso...", "status-neutral");
        try {
            const masksPayload = {
                target: cloneMask(targetMask),
                background: cloneMask(backgroundMask),
            };
            const { response, data } = await runPipeline(pageContext.gaia_source_id, pageContext.sector, masksPayload);
            if (!response.ok || data.status === "error") {
                setStatus("Ricalcolo light curve fallito.", "status-error");
                setError(data.message || `Errore HTTP ${response.status}`);
                output.textContent = JSON.stringify(data, null, 2);
                renderCurrentTpfState();
                return;
            }
            await handlePipelineSuccess(data, "Light curve aggiornata.");
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            setStatus("Errore di rete durante il ricalcolo.", "status-error");
            setError(message);
        } finally {
            setButtonBusy(recalcButton, "Ricalcolo...", false);
            updateEditingControls();
        }
    });

    targetModeButton.addEventListener("click", function () {
        setEditMode("target");
    });

    backgroundModeButton.addEventListener("click", function () {
        setEditMode("background");
    });

    gaiaOverlayToggleButton.addEventListener("click", function () {
        gaiaOverlayEnabled = !gaiaOverlayEnabled;
        updateGaiaOverlayToggleButton();
        renderCurrentTpfState();
        if (lastRunResult && lastRunResult.lightcurve && lastRunResult.lightcurve.available) {
            renderLightcurve(lastRunResult.lightcurve);
        }
    });

    frameSlider.addEventListener("input", function () {
        if (frameSlider.disabled) {
            return;
        }
        setCurrentFrameIndex(parseInt(frameSlider.value, 10));
    });

    saveButton.addEventListener("click", function () {
        saveCurrentResult();
    });

    updateEditingControls();
    updateGaiaOverlayToggleButton();
    renderReturnPayloadPreview(null);
})();
