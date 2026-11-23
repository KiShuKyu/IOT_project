const $ = id => document.getElementById(id);

// ===== Pala Note Project Generator =====

let projectRecorder = null;
let projectChunks = [];
let projectAudioBlob = null;
let projectAudioUrl = null;

$('recordProject').addEventListener('click', async () => {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        projectChunks = [];
        projectAudioBlob = null;

        projectRecorder = new MediaRecorder(stream);

        projectRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                projectChunks.push(event.data);
            }
        };

        projectRecorder.onstop = () => {
            const mime = projectRecorder.mimeType || 'audio/webm';

            projectAudioBlob = new Blob(projectChunks, { type: mime });

            if (projectAudioUrl) {
                URL.revokeObjectURL(projectAudioUrl);
            }

            projectAudioUrl = URL.createObjectURL(projectAudioBlob);

            $('projectPreview').src = projectAudioUrl;
            $('projectPreview').hidden = false;
            $('prepareProject').disabled = false;

            $('projectStatus').textContent = 'Recording ready. Review or prepare your project idea.';

            stream.getTracks().forEach(track => track.stop());
        };

        projectRecorder.start();

        $('recordProject').disabled = true;
        $('stopProject').disabled = false;
        $('prepareProject').disabled = true;
        $('projectProposal').hidden = true;

        $('projectStatus').textContent = 'Listening...';

    } catch (error) {
        $('projectStatus').textContent =
            'Microphone error: ' + error.message;
    }
});


$('stopProject').addEventListener('click', () => {
    if (projectRecorder && projectRecorder.state === 'recording') {
        projectRecorder.stop();

        $('recordProject').disabled = false;
        $('stopProject').disabled = true;
    }
});


$('prepareProject').addEventListener('click', async () => {
    if (!projectAudioBlob) return;

    const formData = new FormData();

    formData.append(
        'audio',
        projectAudioBlob,
        'project-idea.webm'
    );

    $('prepareProject').disabled = true;
    $('projectStatus').textContent = 'Gemini is preparing your project brief...';

    try {
        const response = await fetch('/api/projects/prepare', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Preparation failed');
        }

        $('projectName').value = data.project_name;
        $('projectBrief').value = data.project_brief;

        $('projectProposal').hidden = false;
        $('projectStatus').textContent = 'Project brief ready. Review it before confirming.';

    } catch (error) {
        $('projectStatus').textContent = error.message;

    } finally {
        $('prepareProject').disabled = false;
    }
});


async function waitForProjectCompletion(conversationId) {
    const maxAttempts = 180; // 15 minutes at 5-second intervals

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const response = await fetch(
            `/api/projects/${encodeURIComponent(conversationId)}/status`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Status check failed');
        }

        const status = String(data.execution_status || '').toLowerCase();

        $('generationStatus').textContent =
            `Project generation: ${status || 'working'} (${attempt + 1}/${maxAttempts})`;

        if (status === 'finished') {
            return;
        }

        if (['error', 'failed', 'stopped'].includes(status)) {
            throw new Error(`OpenHands ended with status: ${status}`);
        }

        await new Promise(resolve => setTimeout(resolve, 5000));
    }

    throw new Error('Project generation timed out after 15 minutes');
}


$('confirmProject').addEventListener('click', async () => {
    const projectName = $('projectName').value.trim();
    const projectBrief = $('projectBrief').value.trim();

    if (!projectName || !projectBrief) {
        $('generationStatus').textContent =
            'Project name and brief are required.';
        return;
    }

    $('confirmProject').disabled = true;
    $('generationStatus').textContent = 'Starting OpenHands...';

    try {
        // 1. Start project generation
        const response = await fetch('/api/projects/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                project_name: projectName,
                project_brief: projectBrief,
                confirmed: true
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Project generation failed');
        }

        const conversationId = data.conversation_id;

        $('projectProposal').hidden = true;

        $('generationStatus').textContent =
            `OpenHands is building ${projectName}...`;

        // 2. Poll until the agent finishes
        await waitForProjectCompletion(conversationId);

        $('generationStatus').textContent =
            'Project completed! Preparing your spoken summary...';

        // 3. Request Gemini summary + TTS audio
        const summaryResponse = await fetch(
            `/api/projects/${encodeURIComponent(conversationId)}/spoken-summary?name=${encodeURIComponent(projectName)}`
        );

        const summaryData = await summaryResponse.json();

        if (!summaryResponse.ok) {
            throw new Error(
                summaryData.error || 'Could not generate spoken summary'
            );
        }

        // 4. Display summary
        $('generationStatus').textContent =
            `Project "${projectName}" is ready!\n\n${summaryData.summary}`;

        // 5. Convert Base64 audio to WAV Blob
        const binaryString = atob(summaryData.audio);
        const bytes = new Uint8Array(binaryString.length);

        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        const audioBlob = new Blob(
            [bytes],
            { type: summaryData.audio_mime || 'audio/wav' }
        );

        const audioUrl = URL.createObjectURL(audioBlob);

        // 6. Create audio player
        let audioPlayer = document.getElementById('projectAnnouncement');

        if (!audioPlayer) {
            audioPlayer = document.createElement('audio');
            audioPlayer.id = 'projectAnnouncement';
            audioPlayer.controls = true;
            audioPlayer.style.display = 'block';
            audioPlayer.style.marginTop = '12px';
            $('generationStatus').after(audioPlayer);
        }

        audioPlayer.src = audioUrl;
        audioPlayer.load();

        // 7. Play announcement
        try {
            await audioPlayer.play();
            $('generationStatus').textContent =
                `Project "${projectName}" is ready! Pala Note is speaking...`;
        } catch (playError) {
            $('generationStatus').textContent =
                `Project "${projectName}" is ready!\n\n${summaryData.summary}\n\nPress Play below to hear the announcement.`;
        }

    } catch (error) {
        $('generationStatus').textContent =
            'Project generation failed: ' + error.message;

    } finally {
        $('confirmProject').disabled = false;
    }
});


// ===== Existing Pala Note app code =====

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[c]));
}

function render(container, items) {
    if (!items?.length) {
        container.innerHTML = '<p>No items yet.</p>';
        return;
    }

    container.innerHTML = items.map(i =>
        `<div class="item"><small>${esc(i.kind || 'item')} · ${esc(i.created_at || i.source || '')}</small><h4>${esc(i.title || 'Untitled')}</h4><div>${esc(i.content || '')}</div></div>`
    ).join('');
}

async function refresh() {
    try {
        const h = await fetch('/api/health').then(r => r.json());
        $('health').textContent = `Backend online · Gemini ${h.gemini_configured ? 'configured' : 'missing key'} · Supabase ${h.supabase_configured ? 'configured' : 'not configured'} · ${h.model}`;
    } catch {
        $('health').textContent = 'Health check failed';
    }

    try {
        const r = await fetch('/api/items');
        const data = await r.json();

        if (!r.ok) throw new Error(data.detail || data.error);

        $('count').textContent = `(${data.length})`;
        render($('items'), data);
    } catch (e) {
        $('items').textContent = 'Could not load saved items: ' + e.message;
    }
}

$('form').addEventListener('submit', async ev => {
    ev.preventDefault();

    const file = $('audio').files[0];
    if (!file) return;

    const fd = new FormData();
    fd.append('audio', file);

    $('submit').disabled = true;
    $('submit').textContent = 'Processing…';
    $('status').textContent = 'Sending audio to Gemini…';
    $('transcript').textContent = '';
    $('extracted').innerHTML = '';

    try {
        const r = await fetch('/api/audio', {
            method: 'POST',
            body: fd
        });

        const d = await r.json();

        if (!r.ok) throw new Error(d.detail || d.error || `HTTP ${r.status}`);

        $('status').textContent = `Complete. Saved ${d.saved_count} item(s).`;
        $('transcript').textContent = d.transcript || '(No transcript)';
        render($('extracted'), d.extracted_items);

        await refresh();

    } catch (e) {
        $('status').textContent = 'Processing failed: ' + e.message;

    } finally {
        $('submit').disabled = false;
        $('submit').textContent = 'Process audio';
    }
});

$('refresh').addEventListener('click', refresh);
refresh();


// ===== Manual Project Recall =====

document.getElementById("recallProjectBtn").addEventListener("click", async () => {
    const query = document.getElementById("recallProjectQuery").value.trim();
    const status = document.getElementById("recallProjectStatus");
    const summaryDiv = document.getElementById("recallProjectSummary");
    const audioPlayer = document.getElementById("recallProjectAudio");

    if (!query) {
        status.textContent = "Enter a project name first.";
        return;
    }

    status.textContent = "Searching for project...";
    summaryDiv.textContent = "";
    audioPlayer.hidden = true;
    audioPlayer.pause();

    try {
        const response = await fetch("/api/projects");
        const data = await response.json();

        const projects = data.projects || [];

        const match = projects.find(project =>
            project.project_name.toLowerCase() === query.toLowerCase()
        ) || projects.find(project =>
            project.project_name.toLowerCase().includes(query.toLowerCase()) ||
            project.project_slug.toLowerCase().includes(query.toLowerCase())
        );

        if (!match) {
            status.textContent = "No matching project found.";
            return;
        }

        status.textContent = `Found: ${match.project_name}. Generating summary...`;

        const summaryResponse = await fetch(
            `/api/projects/${match.project_slug}/summary`
        );

        const summaryData = await summaryResponse.json();

        if (!summaryResponse.ok || !summaryData.ok) {
            throw new Error(summaryData.error || "Failed to generate summary.");
        }

        summaryDiv.textContent = summaryData.summary;
        status.textContent = "Project recalled successfully.";

        const binary = atob(summaryData.audio);
        const bytes = new Uint8Array(binary.length);

        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }

        const audioBlob = new Blob([bytes], { type: "audio/wav" });
        const audioUrl = URL.createObjectURL(audioBlob);

        audioPlayer.src = audioUrl;
        audioPlayer.hidden = false;

        audioPlayer.play().catch(error => {
            console.log("Autoplay prevented:", error);
        });

    } catch (error) {
        console.error("Project recall error:", error);
        status.textContent = `Error: ${error.message}`;
    }
});


// ===== Voice Project Recall =====
// This UI is injected beside the existing manual project-recall panel.

(() => {
    const recallAudio = $('recallProjectAudio');
    const recallPanel = recallAudio?.closest('.panel') || recallAudio?.parentElement;

    if (!recallPanel || $('voiceRecallPanel')) return;

    const panel = document.createElement('section');
    panel.id = 'voiceRecallPanel';
    panel.className = 'panel';

    panel.innerHTML = `
        <h2>Voice Recall</h2>
        <p>Ask Pala Note about a project you have already built.</p>
        <div>
            <button type="button" id="voiceRecallStart">Record voice query</button>
            <button type="button" id="voiceRecallStop" disabled>Stop recording</button>
        </div>
        <p id="voiceRecallStatus" aria-live="polite"></p>
        <p><strong>Transcript:</strong></p>
        <div id="voiceRecallTranscript"></div>
        <p><strong>Project summary:</strong></p>
        <div id="voiceRecallSummary"></div>
        <audio id="voiceRecallAudio" controls hidden></audio>
    `;

    recallPanel.insertAdjacentElement('afterend', panel);

    let recorder = null;
    let chunks = [];
    let activeStream = null;
    let audioUrl = null;

    const startButton = $('voiceRecallStart');
    const stopButton = $('voiceRecallStop');
    const status = $('voiceRecallStatus');
    const transcriptDiv = $('voiceRecallTranscript');
    const summaryDiv = $('voiceRecallSummary');
    const audioPlayer = $('voiceRecallAudio');

    startButton.addEventListener('click', async () => {
        try {
            activeStream = await navigator.mediaDevices.getUserMedia({
                audio: true
            });

            chunks = [];
            recorder = new MediaRecorder(activeStream);

            recorder.ondataavailable = event => {
                if (event.data.size > 0) {
                    chunks.push(event.data);
                }
            };

            recorder.onstop = async () => {
                activeStream?.getTracks().forEach(track => track.stop());
                activeStream = null;

                const mime = recorder.mimeType || 'audio/webm';
                const blob = new Blob(chunks, { type: mime });

                const extension = mime.includes('ogg')
                    ? 'ogg'
                    : mime.includes('mp4')
                        ? 'mp4'
                        : 'webm';

                const formData = new FormData();
                formData.append('audio', blob, `voice-recall.${extension}`);

                status.textContent = 'Sending voice query to Pala Note...';
                startButton.disabled = true;
                stopButton.disabled = true;

                try {
                    const response = await fetch('/api/voice-command', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (!response.ok || !data.ok) {
                        throw new Error(
                            data.detail || data.error || 'Voice command failed.'
                        );
                    }

                    transcriptDiv.textContent =
                        data.transcript || '(No transcript returned)';

                    if (data.project_found === false) {
                        summaryDiv.textContent =
                            data.message || 'Could not identify a project.';

                        status.textContent =
                            'Voice query processed, but no project was identified.';
                        return;
                    }

                    if (data.intent !== 'recall_project') {
                        summaryDiv.textContent =
                            data.message ||
                            'This voice query was not recognized as a project-recall request.';

                        status.textContent =
                            `Detected intent: ${data.intent || 'unknown'}`;
                        return;
                    }

                    if (data.project_name) {
                        status.textContent = `Found project: ${data.project_name}`;
                    }

                    summaryDiv.textContent =
                        data.summary || 'No summary was returned.';

                    if (data.audio) {
                        const binary = atob(data.audio);
                        const bytes = new Uint8Array(binary.length);

                        for (let i = 0; i < binary.length; i++) {
                            bytes[i] = binary.charCodeAt(i);
                        }

                        const audioBlob = new Blob(
                            [bytes],
                            { type: 'audio/wav' }
                        );

                        if (audioUrl) {
                            URL.revokeObjectURL(audioUrl);
                        }

                        audioUrl = URL.createObjectURL(audioBlob);
                        audioPlayer.src = audioUrl;
                        audioPlayer.hidden = false;
                        audioPlayer.load();

                        try {
                            await audioPlayer.play();

                            status.textContent =
                                `Project recalled: ${data.project_name || 'project'}. Pala Note is speaking.`;

                        } catch (playError) {
                            status.textContent =
                                `Project recalled: ${data.project_name || 'project'}. Press Play to hear the summary.`;

                            console.log(
                                'Voice recall autoplay prevented:',
                                playError
                            );
                        }

                    } else {
                        status.textContent =
                            `Project recalled: ${data.project_name || 'project'}. No audio was returned.`;
                    }

                } catch (error) {
                    console.error('Voice recall request failed:', error);
                    status.textContent =
                        `Voice recall failed: ${error.message}`;

                } finally {
                    startButton.disabled = false;
                    stopButton.disabled = true;
                }
            };

            recorder.start();

            startButton.disabled = true;
            stopButton.disabled = false;

            transcriptDiv.textContent = '';
            summaryDiv.textContent = '';

            audioPlayer.pause();
            audioPlayer.hidden = true;

            status.textContent =
                'Listening... Say something like: "Tell me about my Expense Tracker project."';

        } catch (error) {
            activeStream?.getTracks().forEach(track => track.stop());
            activeStream = null;

            startButton.disabled = false;
            stopButton.disabled = true;

            status.textContent = `Microphone error: ${error.message}`;
        }
    });

    stopButton.addEventListener('click', () => {
        if (recorder && recorder.state === 'recording') {
            recorder.stop();
            stopButton.disabled = true;
            status.textContent = 'Recording stopped. Processing your request...';
        }
    });
})();