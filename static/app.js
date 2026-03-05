const form = document.getElementById('uploadForm');
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('file');
const imagePreview = document.getElementById('imagePreview');
const statusSection = document.getElementById('statusSection');
const submitBtn = document.getElementById('submitBtn');
const alertBox = document.getElementById('alert');
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        showPreview(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        showPreview(e.target.files[0]);
    }
});

function showPreview(file) {
    if (file && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            imagePreview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
}

function showAlert(message, type) {
    alertBox.textContent = message;
    alertBox.className = `alert alert-${type}`;
    alertBox.style.display = 'block';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        alertBox.style.display = 'none';
    }, 5000);
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(form);
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Submitting. ..';

    try {

        const response = await fetch('/jobs/', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const job = await response.json();
        showStatus(job);
        pollJobStatus(job.id);

        showAlert('Job submitted successfully!', 'success');
    } catch (error) {
        showAlert(error.message, 'error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Start Processing';
    }
});

function showStatus(job) {
    statusSection.classList.add('active');
    document.getElementById('jobId').textContent = job.id;
    document.getElementById('taskType').textContent = job.task_type;
    updateJobStatus(job.status);
    document.getElementById('createdAt').textContent = new Date(job.created_at).toLocaleString();
}

function updateJobStatus(status) {
    const statusEl = document.getElementById('jobStatus');
    const progressFill = document.getElementById('progressFill');

    statusEl.textContent = status;
    statusEl.className = `status-value status-${status.toLowerCase()}`;

    switch (status) {
        case 'PENDING':
            progressFill.style.width = '25%';
            break;
        case 'PROCESSING':
            progressFill.style.width = '75%';
            break;
        case 'COMPLETED':
            progressFill.style.width = '100%';
            break;
        case 'FAILED':
            progressFill.style.width = '100%';
            progressFill.style.background = '#e74c3c';
            break;
    }
}

async function pollJobStatus(jobId) {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/jobs/${jobId}`);
            if (!response.ok) throw new Error('Failed to fetch status');

            const job = await response.json();
            updateJobStatus(job.status);

            if (job.status === 'COMPLETED' || job.status === 'FAILED') {
                clearInterval(interval);
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Start Processing';

                const msgElement = document.getElementById('processingMsg');
                if (msgElement) {
                    msgElement.style.display = "none";
                }

                if (job.result) {
                    const resultBox = document.getElementById('resultBox');
                    resultBox.style.display = 'block';

                    try {
                        const resultData = JSON.parse(job.result);
                        let htmlContent = ``;

                        if (job.status === 'COMPLETED' && resultData.result_image) {
                            const imageUrl = `/jobs/${job.id}/image`;
                            htmlContent += `
                                <div style="margin-top: 20px; text-align: center; border-top: 1px solid #444; pt-20px;">
                                    <h4 style="color: white; margin: 15px 0;">Processed Result:</h4>
                                    <img src="${imageUrl}" style="max-width: 100%; border-radius: 8px; border: 2px solid #667eea;">
                                    <a href="${imageUrl}" download="result_${job.id}.jpg" class="btn" style="display: block; margin-top: 15px; text-decoration: none; line-height: 40px; height: 40px; padding: 0;">
                                        Download Image
                                    </a>
                                </div>`;
                        }
                        resultBox.innerHTML = htmlContent;
                    } catch (err) {
                        console.error("Parse error:", err);
                        resultBox.textContent = "Error parsing result: " + job.result;
                    }
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
            clearInterval(interval);
        }
    }, 2000);
}