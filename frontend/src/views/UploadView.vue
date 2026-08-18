<template>
  <div class="upload-page">
    <nav class="navbar">
      <h1>Pricing Platform</h1>
      <button @click="router.push({ name: 'dashboard' })">Back to Dashboard</button>
    </nav>

    <div class="content">
      <h2>Upload Sales Data</h2>
      <p class="subtitle">Upload your historical sales CSV to train a pricing model</p>

      <div class="upload-card">
        <div
          class="dropzone"
          :class="{ dragging: isDragging }"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="handleDrop"
          @click="fileInput.click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".csv, .xls, .xlsx"
            style="display: none"
            @change="handleFileSelect"
          />
          <div v-if="!selectedFile">
            <p>Drag and drop your CSV file here</p>
            <p class="hint">or click to browse</p>
          </div>
          <div v-else>
            <p>{{ selectedFile.name }}</p>
            <p class="hint">Click to change file</p>
          </div>
        </div>

        <div v-if="error" class="error">{{ error }}</div>

        <div v-if="uploadResult" class="result">
            <div v-if="uploadResult.dataset_warning" class="dataset-warning">
                ⚠️ {{ uploadResult.dataset_warning }}
            </div>
          <h3>Upload Successful</h3>
          <p>Column mapping detected:</p>
          <ul>
            <li>Price column: {{ uploadResult.column_mapping.pricing_column }}</li>
            <li>Demand column: {{ uploadResult.column_mapping.demand_column }}</li>
            <li>Date column: {{ uploadResult.column_mapping.date_column }}</li>
          </ul>
          <div v-if="uploadResult.drift_result" class="drift-warning">
            <p v-if="uploadResult.drift_result.drift_detected">
              ⚠️ Data drift detected in {{ uploadResult.drift_result.drifted_columns.join(', ') }}
            </p>
            <p v-else>✅ No data drift detected</p>
          </div>
          <button @click="proceedToTraining" class="primary-btn">
            Start Training
          </button>
        </div>

        <button
          v-if="selectedFile && !uploadResult"
          @click="handleUpload"
          :disabled="isUploading"
          class="primary-btn"
        >
          {{ isUploading ? 'Uploading...' : 'Upload' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUploadStore } from '@/stores/upload'

const router = useRouter()
const uploadStore = useUploadStore()

const fileInput = ref(null)
const selectedFile = ref(null)
const isDragging = ref(false)
const isUploading = ref(false)
const uploadResult = ref(null)
const error = ref(null)

function handleFileSelect(event) {
  selectedFile.value = event.target.files[0]
  uploadResult.value = null
  error.value = null
}

function handleDrop(event) {
  isDragging.value = false
  const file = event.dataTransfer.files[0]
  const validExtensions = ['.csv', '.xlsx', '.xls']
  const isValid = validExtensions.some(ext => file.name.endsWith(ext))
  if (file && isValid) {
    selectedFile.value = file
    uploadResult.value = null
    error.value = null
  } else {
    error.value = 'Please upload a CSV or Excel file'
  }
}

async function handleUpload() {
  if (!selectedFile.value) return
  isUploading.value = true
  error.value = null
  try {
    uploadResult.value = await uploadStore.uploadFile(selectedFile.value)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Upload failed. Please try again.'
  } finally {
    isUploading.value = false
  }
}

async function proceedToTraining() {
  try {
    await uploadStore.startTraining(uploadResult.value.unique_id)
    router.push({ name: 'training', params: { uniqueId: uploadResult.value.unique_id } })
  } catch {
    error.value = 'Failed to start training. Please try again.'
  }
}
</script>

<style scoped>
.upload-page { min-height: 100vh; background: #f5f5f5; }

.navbar {
  background: white;
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.content { padding: 32px; max-width: 600px; margin: 0 auto; }

.subtitle { color: #666; margin-bottom: 24px; }

.upload-card {
  background: white;
  padding: 32px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.dropzone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 48px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 24px;
  transition: border-color 0.2s;
}

.dropzone.dragging { border-color: #4285f4; background: #f0f4ff; }
.dropzone:hover { border-color: #4285f4; }

.hint { color: #999; font-size: 14px; margin-top: 8px; }

.error {
  color: red;
  background: #fff0f0;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
}

.dataset-warning {
    background: #fffbe6;
    border: 1px solid #ffe58f;
    padding: 12px;
    border-radius: 6px;
    margin-bottom: 16px;
    color: #874d00;
}

.result {
  background: #f0fff4;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.result ul { margin: 8px 0; padding-left: 20px; }
.result li { margin: 4px 0; }

.drift-warning {
  margin-top: 12px;
  padding: 8px;
  background: #fffbe6;
  border-radius: 6px;
}

.primary-btn {
  background: #4285f4;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  width: 100%;
}

.primary-btn:disabled { background: #ccc; cursor: not-allowed; }
</style>
