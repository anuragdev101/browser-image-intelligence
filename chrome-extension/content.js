console.log("MCQ Solver Content Script Loaded (S3 Upload v2.0).");

const TARGET_KEY = 'x';
const REQUIRE_ALT = true;
// Add other modifier consts if needed (REQUIRE_CTRL, REQUIRE_SHIFT)

window.addEventListener('keydown', function(event) {
  const altMatch = REQUIRE_ALT === event.altKey;
  const keyMatch = event.key.toLowerCase() === TARGET_KEY;
  // Add && ctrlMatch etc. if using other modifiers

  if (keyMatch && altMatch) {
    console.log("CS: Alt+X Detected (S3 Flow)!");
    event.preventDefault();
    event.stopPropagation();

    // Send trigger message to background script
    try {
      // Use a descriptive action name
      chrome.runtime.sendMessage({ action: "captureAndUpload" });
      console.log("CS: 'captureAndUpload' message sent to background.");
    } catch (error) {
      console.error("CS: Failed to send message to background:", error);
    }
  }
}, true); // Use capture phase

console.log("MCQ Trigger Key Listener Attached (S3 Upload v2.0).");

// No message listener needed from background in this flow.
// No overlay display needed here.