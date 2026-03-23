(function () {
    const appRoot = document.getElementById("tpfApp");
    const form = document.getElementById("tpfForm");
    const input = document.getElementById("gaiaSourceIdInput");
    const runButton = document.getElementById("runButton");
    const saveButton = document.getElementById("saveButton");
    const statusBox = document.getElementById("statusBox");
    const saveStatusBox = document.getElementById("saveStatusBox");
    const errorBox = document.getElementById("errorBox");
    const output = document.getElementById("output");
    const returnPayloadBox = document.getElementById("returnPayloadBox");
    const targetInfo = document.getElementById("targetInfo");
    const tpfInfo = document.getElementById("tpfInfo");
    const lightcurveInfo = document.getElementById("lightcurveInfo");
    const tpfPlot = document.getElementById("tpfPlot");
    const lightcurvePlot = document.getElementById("lightcurvePlot");

    let lastRunResult = null;

    if (!appRoot || !form || !input || !runButton || !saveButton || !statusBox || !saveStatusBox || !errorBox || !output || !returnPayloadBox || !targetInfo || !tpfInfo || !lightcurveInfo || !tpfPlot || !lightcurvePlot) {
        return;
    }

    const appContext = {
        runUrl: appRoot.dataset.runUrl || "/tpf/api/run",
        saveUrl: appRoot.dataset.saveUrl || "/tpf/api/save",
        initialGaiaSourceId: appRoot.dataset.initialGaiaSourceId || "",
        sourceContext: appRoot.dataset.sourceContext || "",
        entryMode: appRoot.dataset.entryMode || "standalone",
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

    function clearPlots() {
        Plotly.purge(tpfPlot);
        Plotly.purge(lightcurvePlot);
        tpfPlot.innerHTML = "";
        lightcurvePlot.innerHTML = "";
    }

    function resetSections() {
        renderTarget(null);
        tpfInfo.textContent = "TPF non ancora richiesta.";
        lightcurveInfo.textContent = "Light curve non ancora richiesta.";
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

    function renderTPF(grid) {
        const data = [{
            z: grid,
            type: "heatmap",
            colorscale: "Viridis",
            hoverongaps: false,
        }];
        const layout = {
            title: "TPF Flux Grid Preview",
            margin: { t: 40, r: 20, b: 40, l: 40 },
            xaxis: { title: "Pixel X", constrain: "domain" },
            yaxis: { title: "Pixel Y", autorange: "reversed", scaleanchor: "x", scaleratio: 1 },
        };
        Plotly.newPlot(tpfPlot, data, layout, { responsive: true, displayModeBar: false });
    }

    function renderLightcurve(time, flux) {
        const trace = {
            x: time,
            y: flux,
            mode: "lines",
            name: "Flux",
            line: { color: "#2f7ed8" },
        };
        const layout = {
            title: "Light Curve",
            margin: { t: 40, r: 20, b: 40, l: 50 },
            xaxis: { title: "Time" },
            yaxis: { title: "Flux" },
        };
        Plotly.newPlot(lightcurvePlot, [trace], layout, { responsive: true, displayModeBar: false });
    }

    function updateSections(data) {
        renderTarget(data.target || null);

        if (data.tpf && data.tpf.available && Array.isArray(data.tpf.flux_grid)) {
            tpfInfo.textContent = data.tpf.message || "TPF disponibile.";
            renderTPF(data.tpf.flux_grid);
        } else {
            tpfInfo.textContent = data.tpf && data.tpf.message ? data.tpf.message : "TPF non disponibile.";
            Plotly.purge(tpfPlot);
            tpfPlot.innerHTML = "";
        }

        if (data.lightcurve && data.lightcurve.available && Array.isArray(data.lightcurve.time) && Array.isArray(data.lightcurve.flux)) {
            lightcurveInfo.textContent = data.lightcurve.message || "Light curve disponibile.";
            renderLightcurve(data.lightcurve.time, data.lightcurve.flux);
        } else {
            lightcurveInfo.textContent = data.lightcurve && data.lightcurve.message ? data.lightcurve.message : "Light curve non disponibile.";
            Plotly.purge(lightcurvePlot);
            lightcurvePlot.innerHTML = "";
        }
    }

    function buildAgataReturnPayload(result) {
        if (!result || result.status !== "ok") {
            return {
                status: "ok",
                message: "Nessun risultato pronto",
                agata_context: {
                    entry_mode: appContext.entryMode,
                    source_context: appContext.sourceContext || null,
                },
            };
        }

        return {
            status: "ok",
            message: "Payload di ritorno AGATA pronto",
            agata_context: {
                entry_mode: appContext.entryMode,
                source_context: appContext.sourceContext || null,
            },
            input: {
                gaia_source_id: result.input && result.input.gaia_source_id ? result.input.gaia_source_id : null,
            },
            target_summary: result.target ? {
                gaia_source_id: result.target.gaia_source_id || null,
                catalog: result.target.catalog || null,
                ra_deg: result.target.ra_deg ?? null,
                dec_deg: result.target.dec_deg ?? null,
                gmag: result.target.gmag ?? null,
            } : null,
            availability: {
                tpf: !!(result.tpf && result.tpf.available),
                lightcurve: !!(result.lightcurve && result.lightcurve.available),
            },
            save_summary: result.save ? {
                mode: result.save.mode || null,
                saved: !!result.save.saved,
                save_id: result.save.save_id || null,
                saved_at_utc: result.save.saved_at_utc || null,
            } : null,
        };
    }

    function renderReturnPayloadPreview(result) {
        returnPayloadBox.textContent = JSON.stringify(buildAgataReturnPayload(result), null, 2);
    }

    async function runPipeline(gaiaSourceId) {
        const response = await fetch(appContext.runUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                gaia_source_id: gaiaSourceId,
                source_context: appContext.sourceContext || null,
            }),
        });
        const data = await response.json().catch(() => ({ status: "error", message: "Risposta JSON non valida" }));
        output.textContent = JSON.stringify(data, null, 2);

        if (!response.ok || data.status === "error") {
            lastRunResult = null;
            saveButton.disabled = true;
            setStatus(data.message || "Pipeline completata con errore.", "status-error");
            setError(data.message || `Errore HTTP ${response.status}`);
            renderReturnPayloadPreview(null);
            updateSections(data || {});
            return;
        }

        lastRunResult = data;
        saveButton.disabled = false;
        const tpfAvailable = !!(data.tpf && data.tpf.available);
        const lcAvailable = !!(data.lightcurve && data.lightcurve.available);
        setStatus(
            data.message || `Pipeline completata | TPF: ${tpfAvailable ? "disponibile" : "non disponibile"} | Light curve: ${lcAvailable ? "disponibile" : "non disponibile"}`,
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
                agata_context: {
                    entry_mode: appContext.entryMode,
                    source_context: appContext.sourceContext || null,
                },
            };
            const response = await fetch(appContext.saveUrl, {
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

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const gaiaSourceId = String(input.value || "").trim();
        setError("");
        setStatus("Loading... esecuzione pipeline in corso.", "status-neutral");
        setSaveStatus("Nessun salvataggio eseguito.", "status-neutral");
        output.textContent = JSON.stringify({ status: "ok", message: "Loading..." }, null, 2);
        lastRunResult = null;
        saveButton.disabled = true;
        setButtonBusy(runButton, "Loading...", true);
        clearPlots();
        resetSections();
        renderReturnPayloadPreview(null);

        try {
            await runPipeline(gaiaSourceId);
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

    renderReturnPayloadPreview(null);

    saveButton.addEventListener("click", function () {
        saveCurrentResult();
    });
})();
