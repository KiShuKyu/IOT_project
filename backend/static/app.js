
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

            $('projectStatus').textContent =
                'Recording ready. Review or prepare your project idea.';

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
    $('projectStatus').textContent =
        'Gemini is preparing your project brief...';

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
        $('projectStatus').textContent =
            'Project brief ready. Review it before confirming.';

    } catch (error) {
        $('projectStatus').textContent = error.message;

    } finally {
        $('prepareProject').disabled = false;
    }
});


async function waitForProjectCompletion(conversationId) {
    const maxAttempts = 180;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const response = await fetch(
            `/api/projects/${encodeURIComponent(conversationId)}/status`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Status check failed');
        }

        const status = String(
            data.execution_status || ''
        ).toLowerCase();

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

        await waitForProjectCompletion(conversationId);

        $('generationStatus').textContent =
            'Project completed! Preparing your spoken summary...';

        const summaryResponse = await fetch(
            `/api/projects/${encodeURIComponent(conversationId)}/spoken-summary?name=${encodeURIComponent(projectName)}`
        );

        const summaryData = await summaryResponse.json();

        if (!summaryResponse.ok) {
            throw new Error(
                summaryData.error || 'Could not generate spoken summary'
            );
        }

        $('generationStatus').textContent =
            `Project "${projectName}" is ready!\n\n${summaryData.summary}`;

        if (summaryData.audio) {
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

            try {
                await audioPlayer.play();

                $('generationStatus').textContent =
                    `Project "${projectName}" is ready! Pala Note is speaking.`;

            } catch (playError) {
                $('generationStatus').textContent =
                    `Project "${projectName}" is ready!\n\n${summaryData.summary}\n\nPress Play below to hear the announcement.`;
            }
        }

    } catch (error) {
        $('generationStatus').textContent =
            'Project generation failed: ' + error.message;

    } finally {
        $('confirmProject').disabled = false;
    }
});


// ===== Existing Pala Note App =====

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
        `<div class="item">
            <small>${esc(i.kind || 'item')} · ${esc(i.created_at || i.source || '')}</small>
            <h4>${esc(i.title || 'Untitled')}</h4>
            <div>${esc(i.content || '')}</div>
        </div>`
    ).join('');
}


async function refresh() {
    try {
        const h = await fetch('/api/health').then(r => r.json());

        $('health').textContent =
            `Backend online · Gemini ${h.gemini_configured ? 'configured' : 'missing key'} · Supabase ${h.supabase_configured ? 'configured' : 'not configured'} · ${h.model}`;

    } catch {
        $('health').textContent = 'Health check failed';
    }

    try {
        const r = await fetch('/api/items');
        const data = await r.json();

        if (!r.ok) {
            throw new Error(data.detail || data.error);
        }

        $('count').textContent = `(${data.length})`;
        render($('items'), data);

    } catch (e) {
        $('items').textContent =
            'Could not load saved items: ' + e.message;
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

        if (!r.ok) {
            throw new Error(d.detail || d.error || `HTTP ${r.status}`);
        }

        $('status').textContent =
            `Complete. Saved ${d.saved_count} item(s).`;

        $('transcript').textContent =
            d.transcript || '(No transcript)';

        render($('extracted'), d.extracted_items);

        await refresh();

    } catch (e) {
        $('status').textContent =
            'Processing failed: ' + e.message;

    } finally {
        $('submit').disabled = false;
        $('submit').textContent = 'Process audio';
    }
});


$('refresh').addEventListener('click', refresh);
refresh();


// ===== Manual Project Recall =====

$('recallProjectBtn').addEventListener('click', async () => {
    const query = $('recallProjectQuery').value.trim();
    const status = $('recallProjectStatus');
    const summaryDiv = $('recallProjectSummary');
    const audioPlayer = $('recallProjectAudio');

    if (!query) {
        status.textContent = 'Enter a project name first.';
        return;
    }

    status.textContent = 'Searching for project...';
    summaryDiv.textContent = '';
    audioPlayer.hidden = true;
    audioPlayer.pause();

    try {
        const response = await fetch('/api/projects');
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Could not load projects');
        }

        const projects = data.projects || [];

        const match = projects.find(project =>
            project.project_name.toLowerCase() === query.toLowerCase()
        ) || projects.find(project =>
            project.project_name.toLowerCase().includes(query.toLowerCase()) ||
            project.project_slug.toLowerCase().includes(query.toLowerCase())
        );

        if (!match) {
            status.textContent = 'No matching project found.';
            return;
        }

        status.textContent =
            `Found: ${match.project_name}. Generating summary...`;

        const summaryResponse = await fetch(
            `/api/projects/${encodeURIComponent(match.project_slug)}/summary`
        );

        const summaryData = await summaryResponse.json();

        if (!summaryResponse.ok || !summaryData.ok) {
            throw new Error(
                summaryData.error || 'Failed to generate summary.'
            );
        }

        summaryDiv.textContent = summaryData.summary;
        status.textContent = 'Project recalled successfully.';

        // Keep project conversation UI in sync.
        window.dispatchEvent(new CustomEvent('pala:active-project', {
            detail: {
                project_name: summaryData.project_name,
                project_slug: summaryData.project_slug
            }
        }));

        if (summaryData.audio) {
            const binary = atob(summaryData.audio);
            const bytes = new Uint8Array(binary.length);

            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }

            const audioBlob = new Blob(
                [bytes],
                { type: 'audio/wav' }
            );

            const audioUrl = URL.createObjectURL(audioBlob);

            audioPlayer.src = audioUrl;
            audioPlayer.hidden = false;

            audioPlayer.play().catch(error => {
                console.log('Autoplay prevented:', error);
            });

        } else {
            audioPlayer.hidden = true;

            if (summaryData.audio_error) {
                status.textContent = summaryData.audio_error;
            }
        }

    } catch (error) {
        console.error('Project recall error:', error);
        status.textContent = `Error: ${error.message}`;
    }
});


// ===== Project Conversation: Voice + Text Follow-ups =====

(() => {
    const panel = $('voiceRecallPanel');
    if (!panel) return;

    const startButton = $('voiceRecallStart');
    const stopButton = $('voiceRecallStop');
    const status = $('voiceRecallStatus');
    const transcriptDiv = $('voiceRecallTranscript');
    const answerDiv = $('voiceRecallSummary');
    const audioPlayer = $('voiceRecallAudio');
    const questionInput = $('voiceRecallQuestion');
    const askButton = $('voiceRecallAsk');
    const activeProjectLabel = $('voiceRecallActiveProject');
    const clearButton = $('voiceRecallClear');
    const conversation = $('voiceRecallConversation');

    let recorder = null;
    let chunks = [];
    let activeStream = null;
    let audioUrl = null;


    function setActiveProject(name) {
        activeProjectLabel.textContent = name
            ? `Active project: ${name}`
            : 'No active project. Recall a project first.';
    }


    function addMessage(role, text) {
        const item = document.createElement('div');

        item.className =
            `project-chat-message ${role === 'user' ? 'user' : 'assistant'}`;

        const label = document.createElement('strong');

        label.textContent =
            role === 'user' ? 'You' : 'Pala Note';

        const body = document.createElement('p');
        body.textContent = text;

        item.append(label, body);
        conversation.appendChild(item);

        conversation.scrollTop = conversation.scrollHeight;
    }


    function playAudio(base64Audio) {
        if (!base64Audio) {
            audioPlayer.hidden = true;
            return Promise.resolve(false);
        }

        const binary = atob(base64Audio);
        const bytes = new Uint8Array(binary.length);

        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }

        const blob = new Blob(
            [bytes],
            { type: 'audio/wav' }
        );

        if (audioUrl) {
            URL.revokeObjectURL(audioUrl);
        }

        audioUrl = URL.createObjectURL(blob);

        audioPlayer.src = audioUrl;
        audioPlayer.hidden = false;
        audioPlayer.load();

        return audioPlayer.play()
            .then(() => true)
            .catch(() => false);
    }


    async function showProjectResponse(data, userText) {
        const answer =
            data.answer ||
            data.summary ||
            data.message ||
            'No answer was returned.';

        if (userText) {
            addMessage('user', userText);
        }

        addMessage('assistant', answer);

        answerDiv.textContent = answer;

        if (data.project_name) {
            setActiveProject(data.project_name);
        }

        if (data.transcript) {
            transcriptDiv.textContent = data.transcript;
        }

        if (data.audio) {
            const played = await playAudio(data.audio);

            status.textContent = played
                ? `Answered using ${data.project_name || 'the active project'}. Pala Note is speaking.`
                : `Answer ready for ${data.project_name || 'the active project'}. Press Play to hear it.`;

        } else {
            audioPlayer.hidden = true;

            status.textContent =
                data.audio_error ||
                `Answer ready for ${data.project_name || 'the active project'}.`;
        }
    }


    async function loadActiveProject() {
        try {
            const response = await fetch('/api/project-context');
            const data = await response.json();

            if (response.ok && data.active) {
                setActiveProject(data.project_name);
            } else {
                setActiveProject('');
            }

        } catch (error) {
            console.warn(
                'Could not load active project context:',
                error
            );
        }
    }


    // Sync the project label when manual recall selects a project.
    window.addEventListener('pala:active-project', event => {
        setActiveProject(event.detail?.project_name || '');
    });


    // ===== Typed follow-up =====

    async function askTypedQuestion() {
        const question = questionInput.value.trim();

        if (!question) {
            status.textContent = 'Type a question first.';
            return;
        }

        askButton.disabled = true;
        status.textContent =
            'Pala Note is checking the active project...';

        audioPlayer.pause();
        audioPlayer.hidden = true;

        try {
            const response = await fetch('/api/project-chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question })
            });

            const data = await response.json();

            if (!response.ok || !data.ok) {
                throw new Error(
                    data.error ||
                    data.detail ||
                    `HTTP ${response.status}`
                );
            }

            questionInput.value = '';

            await showProjectResponse(data, question);

        } catch (error) {
            status.textContent =
                `Follow-up failed: ${error.message}`;

        } finally {
            askButton.disabled = false;
        }
    }


    askButton.addEventListener('click', askTypedQuestion);

    questionInput.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            askTypedQuestion();
        }
    });


    // ===== Clear active project =====

    clearButton.addEventListener('click', async () => {
        try {
            const response = await fetch(
                '/api/project-chat/reset',
                { method: 'POST' }
            );

            const data = await response.json();

            if (!response.ok || !data.ok) {
                throw new Error(
                    data.error || 'Could not clear context'
                );
            }

            setActiveProject('');
            conversation.innerHTML = '';
            transcriptDiv.textContent = '';
            answerDiv.textContent = '';

            audioPlayer.pause();
            audioPlayer.hidden = true;

            status.textContent = 'Active project cleared.';

        } catch (error) {
            status.textContent =
                `Could not clear project: ${error.message}`;
        }
    });


    // ===== Voice follow-up =====

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

                formData.append(
                    'audio',
                    blob,
                    `voice-recall.${extension}`
                );

                startButton.disabled = true;
                stopButton.disabled = true;

                status.textContent =
                    'Transcribing and answering...';

                try {
                    const response = await fetch('/api/voice-command', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (!response.ok || !data.ok) {
                        throw new Error(
                            data.detail ||
                            data.error ||
                            `HTTP ${response.status}`
                        );
                    }

                    transcriptDiv.textContent =
                        data.transcript || '(No transcript returned)';

                    if (data.context_cleared) {
                        setActiveProject('');
                        conversation.innerHTML = '';
                        answerDiv.textContent = '';
                        audioPlayer.pause();
                        audioPlayer.hidden = true;

                        status.textContent =
                            data.message || 'Active project cleared.';

                        return;
                    }

                    if (
                        data.project_found === false ||
                        (!data.project_name && data.message)
                    ) {
                        status.textContent =
                            data.message || 'No project was identified.';

                        if (data.message) {
                            addMessage('assistant', data.message);
                        }

                        return;
                    }

                    await showProjectResponse(
                        data,
                        data.transcript || 'Voice question'
                    );

                } catch (error) {
                    console.error(
                        'Voice recall request failed:',
                        error
                    );

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

            status.textContent =
                'Listening... Ask about the active project, or say a new project name to switch.';

            audioPlayer.pause();
            audioPlayer.hidden = true;

        } catch (error) {
            activeStream?.getTracks().forEach(track => track.stop());
            activeStream = null;

            startButton.disabled = false;
            stopButton.disabled = true;

            status.textContent =
                `Microphone error: ${error.message}`;
        }
    });


    stopButton.addEventListener('click', () => {
        if (recorder && recorder.state === 'recording') {
            recorder.stop();

            stopButton.disabled = true;

            status.textContent =
                'Recording stopped. Processing your question...';
        }
    });


    // Load any project already selected in this browser session.
    loadActiveProject();

})();
