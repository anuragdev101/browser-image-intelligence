console.log("MCQ Solver Background SW Started (S3 Upload v2.1 - Secured).");

// --- Configuration ---
const GET_UPLOAD_URL_ENDPOINT = "YOUR_UPLOAD_URL"; // e.g., https://<...>/get-upload-url
// !!! REPLACE with HttpApiTriggerUrl Output !!!
const TRIGGER_RELAY_ENDPOINT = "YOUR_TRIGGER_URL"; 
// !!! ADD YOUR API KEY VALUE HERE - Acquired After CFN Deploy & Manual Retrieval !!!
const API_KEY_VALUE = "YOUR_APIGATEWAY_API_KEY";


// Helper function to convert Data URL to Blob (Unchanged)
async function dataUrlToBlob(dataUrl) {
  try {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    console.log("BG DEBUG: dataUrlToBlob conversion successful.");
    return blob;
  } catch (error) {
    console.error("BG DEBUG ERROR in dataUrlToBlob:", error);
    throw error;
  }
}


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("BG: Received message:", message);

  if (message.action === "captureAndUpload") {
    console.log("BG: 'captureAndUpload' action received.");

    // Capture Tab
    chrome.tabs.captureVisibleTab(null, { format: "png" }, async (dataUrl) => {
      console.log("BG DEBUG: captureVisibleTab callback executed.");
      if (chrome.runtime.lastError || !dataUrl) {
        console.error("BG ERROR: captureVisibleTab failed:", chrome.runtime.lastError?.message || "No data URL");
        return;
      }
      console.log("BG: Tab captured successfully.");

      // Async block for S3/Relay
      (async () => {
        try {
          // Stage 2: Get Pre-signed URL
          console.log("BG DEBUG: Checking GET_UPLOAD_URL_ENDPOINT config...");
          if (!GET_UPLOAD_URL_ENDPOINT || GET_UPLOAD_URL_ENDPOINT.includes("YOUR_HTTP_API_GET_UPLOAD_URL")) {
             throw new Error("Config Error: Get Upload URL Lambda endpoint missing.");
          }
          if (!API_KEY_VALUE || API_KEY_VALUE === "YOUR_ACTUAL_API_KEY_VALUE_HERE") {
             throw new Error("Config Error: API_KEY_VALUE missing in background.js.");
          }
          console.log(`BG DEBUG: Requesting pre-signed URL from ${GET_UPLOAD_URL_ENDPOINT}...`);
          const urlResponse = await fetch(GET_UPLOAD_URL_ENDPOINT, {
              method: 'POST',
              headers: {
                  // 'Content-Type': 'application/json', // Only needed if sending a body
                  'x-api-key': API_KEY_VALUE // <<< ADDED API KEY HEADER
              }
              // body: JSON.stringify({ filename: 'screenshot.png' }) // Optional: Send data if Lambda needs it
          });
          console.log(`BG: Get Upload URL Lambda Response Status: ${urlResponse.status}`);
          if (!urlResponse.ok) {
            const errorText = await urlResponse.text();
            throw new Error(`Get URL Lambda request failed: ${urlResponse.status}. ${errorText}`);
          }
          const presignedData = await urlResponse.json();
           if (!presignedData.uploadUrl || !presignedData.fields || !presignedData.key) {
             throw new Error("Invalid pre-signed URL data received.");
          }
          console.log("BG: Received pre-signed POST data. Key:", presignedData.key);

          // Stage 3: Upload Image Blob to S3
          console.log("BG DEBUG: Converting Data URL to Blob...");
          const imageBlob = await dataUrlToBlob(dataUrl);
          console.log(`BG: Blob created. Uploading to S3 (${imageBlob.size} bytes)...`);
          const formData = new FormData();
          Object.entries(presignedData.fields).forEach(([key, value]) => { formData.append(key, value); });
          formData.append('file', imageBlob, presignedData.key);
          const s3UploadResponse = await fetch(presignedData.uploadUrl, { method: 'POST', body: formData });
          console.log(`BG: S3 Upload Response Status: ${s3UploadResponse.status}`);
          if (!s3UploadResponse.ok) {
             const errorText = await s3UploadResponse.text();
             throw new Error(`S3 upload failed: ${s3UploadResponse.status}. ${errorText}`);
          }
          console.log("BG: Image successfully uploaded to S3.");

          // Stage 4: Trigger Relay Lambda
          console.log("BG DEBUG: Checking TRIGGER_RELAY_ENDPOINT config...");
           if (!TRIGGER_RELAY_ENDPOINT || TRIGGER_RELAY_ENDPOINT.includes("YOUR_HTTP_API_TRIGGER_URL_HERE")) {
              throw new Error("Config Error: Trigger URL endpoint missing.");
          }
          console.log(`BG DEBUG: Triggering Relay Lambda at ${TRIGGER_RELAY_ENDPOINT}...`);
          const relayResponse = await fetch(TRIGGER_RELAY_ENDPOINT, {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
                  'x-api-key': API_KEY_VALUE // <<< ADDED API KEY HEADER
                  },
              body: JSON.stringify({ action: "relayS3Key", s3Key: presignedData.key })
          });
          console.log(`BG: Relay Lambda Response Status: ${relayResponse.status}`);
           if (!relayResponse.ok) {
               const relayErrorText = await relayResponse.text();
               console.error(`BG ERROR: Relay Lambda invocation failed: ${relayResponse.status}. ${relayErrorText}`);
          } else {
               const relayData = await relayResponse.json();
               console.log("BG: Relay Lambda invoked successfully:", relayData);
          }
          console.log("BG DEBUG: Full sequence complete.");

        } catch (error) {
           console.error("BG ERROR during async S3/Relay process:", error.message);
        }
      })(); // End IIAFE

    }); // End captureVisibleTab callback
    return true; // Indicate async work
  } // End if
  return false; // Default return
});

self.addEventListener('unhandledrejection', event => { console.error('BG ERROR: Unhandled promise rejection:', event.reason); });
console.log("MCQ Solver Background SW Ready (Chrome S3 v2.1 - Secured).");