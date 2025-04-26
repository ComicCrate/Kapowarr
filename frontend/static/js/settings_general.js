// Add references for new/changed elements
// Change const to let for variables that are assigned inside DOMContentLoaded
let cvKeysList = document.querySelector('#cv-keys-list'); // Changed from const
let newCvKeyInput = document.querySelector('#new-cv-key-input'); // Changed from const
let addCvKeyButton = document.querySelector('#add-cv-key-button'); // Changed from const
// References for the new URL select and custom input
let cvUrlSelect = document.querySelector('#cv-url-select'); // Changed from const
let cvUrlCustomInput = document.querySelector('#cv-url-custom-input'); // Changed from const
// Get the template row for a CV key entry from the pre-build-els table
let cvKeyEntryTemplate = document.querySelector('.pre-build-els .cv-key-entry'); // Changed from const


// --- Debugging: Check if essential elements are found and log details immediately ---
// This check is now outside DOMContentLoaded, like the working version's approach
console.log('settings_general.js script started.');
if (!cvKeyEntryTemplate) console.error("Template Element (.pre-build-els .cv-key-entry) is NULL before DOMContentLoaded!");
if (!cvKeysList) console.error("List Container Element (#cv-keys-list) is NULL before DOMContentLoaded!");
if (!addCvKeyButton) console.error("Add Button Element (#add-cv-key-button) is NULL before DOMContentLoaded!");
if (!newCvKeyInput) console.error("New Key Input Element (#new-cv-key-input) is NULL before DOMContentLoaded!");
if (!cvUrlSelect) console.error("CV URL Select Element (#cv-url-select) is NULL before DOMContentLoaded!");
if (!cvUrlCustomInput) console.error("CV URL Custom Input Element (#cv-url-custom-input) is NULL before DOMContentLoaded!");

// Check if all essential elements are found before DOMContentLoaded
if (!cvKeyEntryTemplate || !cvKeysList || !addCvKeyButton || !newCvKeyInput || !cvUrlSelect || !cvUrlCustomInput) {
    console.warn("One or more essential elements not found before DOMContentLoaded. May be assigned later.");
} else {
    console.log("All essential elements found before DOMContentLoaded.");
}
// ------------------------------------------------------------------------------------


// Helper to create a row for the CV key list from the template
function createCvKeyRow(apiKey) {
    // Check if the template was found (should be available from pre_build_rows)
    if (!cvKeyEntryTemplate) {
        console.error("CV key entry template is null during createCvKeyRow! Cannot create row.");
        return null; // Return null if template is not available
    }

    const row = cvKeyEntryTemplate.cloneNode(true); // Clone the template row
    const displayInput = row.querySelector('.cv-key-display');
    const deleteButton = row.querySelector('.delete-cv-key');

    // Set the value of the display input (masked) and store the full key
    // You might want to adjust the masking logic based on preference
    displayInput.value = apiKey ? apiKey.substring(0, 4) + '...' + apiKey.substring(apiKey.length - 4) : '';
    displayInput.title = apiKey; // Show full key on hover
    displayInput.dataset.fullKey = apiKey; // Store full key in data attribute

    // Add delete functionality to the button
    deleteButton.onclick = () => row.remove();

    return row; // Return the created table row element
}


// Helper to get current keys from the UI list
function getCvKeysFromUI() {
    // Select input elements within the list container and get their full key data attribute
    if (!cvKeysList) {
        console.error("CV keys list container is null during getCvKeysFromUI!");
        return []; // Return empty array if container is not available
    }
    return [...cvKeysList.querySelectorAll('.cv-key-entry .cv-key-display')]
        .map(input => input.dataset.fullKey)
        .filter(key => key); // Filter out any potentially undefined or empty ones
}


function fillSettings(api_key) {
    fetchAPI('/settings', api_key)
    .then(json => {
       const settings = json.result; // Store result for easier access

       document.querySelector('#bind-address-input').value = settings.host;
       document.querySelector('#port-input').value = settings.port;
       document.querySelector('#url-base-input').value = settings.url_base;
       document.querySelector('#password-input').value = settings.auth_password;
       document.querySelector('#api-key-display').value = api_key; // Use new ID

       // Populate CV Keys list
       if (cvKeysList) { // Check if container is available
           cvKeysList.innerHTML = ''; // Clear previous entries
           (settings.comicvine_api_keys || []).forEach(key => {
              if (key) { // Ensure key is not empty before adding
                 const keyRow = createCvKeyRow(key);
                 if (keyRow) { // Check if row creation was successful
                    cvKeysList.appendChild(keyRow);
                 }
              }
           });
       } else {
            console.error("CV keys list container is null during fillSettings! Cannot populate list.");
       }


       // --- Updated: Fill CV API URL Select/Input ---
        if (cvUrlSelect && cvUrlCustomInput) { // Check if URL elements are available
            const savedUrl = settings.comicvine_api_url || ''; // Get saved URL
            let urlMatch = false;
            // Check if saved URL matches predefined options
            for (let option of cvUrlSelect.options) {
                // Check against option's value, ensure it's not the 'custom' value itself
                if (option.value === savedUrl && option.value !== 'custom') {
                    option.selected = true;
                    urlMatch = true;
                    break;
                }
            }

            if (urlMatch) {
                // Matched a predefined option
                cvUrlCustomInput.classList.add('hidden'); // Hide custom input
                cvUrlCustomInput.value = ''; // Clear custom input
                 // Ensure 'custom' is not selected if a predefined option matched
                 // This specific check might not be strictly necessary if logic flows correctly,
                 // but can prevent odd states if the dropdown value was previously 'custom'.
                 if (cvUrlSelect.value === 'custom' && savedUrl !== 'custom') {
                     cvUrlSelect.value = savedUrl; // Reset dropdown value to the matched option
                 }
            } else if (savedUrl) {
                // No predefined match, but URL exists -> must be custom
                cvUrlSelect.value = 'custom';
                cvUrlCustomInput.value = savedUrl;
                cvUrlCustomInput.classList.remove('hidden'); // Show custom input
            } else {
                // No URL saved or saved URL is empty, select default and hide custom
                 // Find the default option value (usually the first one, assuming it's not 'custom')
                 const defaultOption = cvUrlSelect.options[0]?.value || '';
                 cvUrlSelect.value = defaultOption; // Set dropdown to default
                 cvUrlCustomInput.classList.add('hidden');
                 cvUrlCustomInput.value = '';
            }
        } else {
            console.error("CV URL select or custom input not found during fillSettings! Cannot populate URL setting.");
        }
        // ----------------------------------------------

       document.querySelector('#flaresolverr-input').value = settings.flaresolverr_base_url;
       document.querySelector('#log-level-input').value = settings.log_level;
       // Fill theme separately as it's not part of the API settings fetch
       document.querySelector('#theme-input').value = getLocalStorage('theme')['theme'];
    })
    .catch(error => {
        console.error("Error fetching settings:", error);
         // Handle fetch error - perhaps display a message to the user
         // You might want to show an error message on the page here.
    });
};

function saveSettings(api_key) {
    document.querySelector("#save-button p").innerText = 'Saving';
    // Clear previous errors from UI elements
    document.querySelectorAll('.cv-key-display').forEach(input => input.classList.remove('error-input')); // Assuming error class applies to the display input
    document.querySelector('#new-cv-key-input').classList.remove('error-input');
    document.querySelector('#cv-keys-error').classList.add('hidden'); // Hide general CV keys error
    document.querySelector('#cv-url-error').classList.add('hidden'); // Hide CV URL error
    document.querySelector("#flaresolverr-input").classList.remove('error-input');
    if (cvUrlCustomInput) cvUrlCustomInput.classList.remove('error-input'); // Check before accessing


    const currentCvKeys = getCvKeysFromUI(); // Get keys from UI list

    // Basic validation for CV keys (frontend check)
    if (currentCvKeys.length === 0) {
       document.querySelector('#cv-keys-error').classList.remove('hidden');
       document.querySelector("#save-button p").innerText = 'Failed';
       return; // Stop saving if no keys are present
    }

    // --- Get CV API URL based on selection ---
    let comicvineApiUrl = '';
    if (cvUrlSelect && cvUrlCustomInput) { // Check if URL elements are available
        const selectedUrlOption = cvUrlSelect.value;

        if (selectedUrlOption === 'custom') {
            comicvineApiUrl = cvUrlCustomInput.value.trim();
            // Add validation for custom URL if needed (basic frontend check)
            if (!comicvineApiUrl) {
                 document.querySelector('#cv-url-error').innerText = '*Custom URL cannot be empty when selected.';
                 document.querySelector('#cv-url-error').classList.remove('hidden');
                 cvUrlCustomInput.classList.add('error-input');
                 document.querySelector("#save-button p").innerText = 'Failed';
                 return; // Stop saving
            }
            // Basic URL format check (optional, backend validates more thoroughly)
            try {
                if (!comicvineApiUrl.startsWith('http://') && !comicvineApiUrl.startsWith('https://')) {
                    throw new Error("URL must start with http:// or https://");
                }
                new URL(comicvineApiUrl); // Test parsing
            } catch (err) {
                 document.querySelector('#cv-url-error').innerText = `*Invalid Custom URL format: ${err.message}.`;
                 document.querySelector('#cv-url-error').classList.remove('hidden');
                 cvUrlCustomInput.classList.add('error-input');
                 document.querySelector("#save-button p").innerText = 'Failed';
                return; // Stop saving
            }
        } else {
            comicvineApiUrl = selectedUrlOption; // Use the value from the selected predefined option
        }
    } else {
         console.error("CV URL select or custom input not found during saveSettings!");
         // Decide how to handle this - maybe proceed without URL? Or stop?
         // For now, let's proceed but log the error. Backend should also validate.
    }
    // ----------------------------------------------------


    const data = {
       'host': document.querySelector('#bind-address-input').value,
       'port': parseInt(document.querySelector('#port-input').value),
       'url_base': document.querySelector('#url-base-input').value,
       'auth_password': document.querySelector('#password-input').value,
       'comicvine_api_keys': currentCvKeys, // Send the list of keys
       'comicvine_api_url': comicvineApiUrl, // Include the determined URL
       'flaresolverr_base_url': document.querySelector('#flaresolverr-input').value,
       'log_level': parseInt(document.querySelector('#log-level-input').value)
    };

    sendAPI('PUT', '/settings', api_key, {}, data)
    .then(response => { // Check response status before assuming success
        if (!response.ok) return Promise.reject(response);
        return response.json();
    })
    .then(json => {
       if (json.error !== null) return Promise.reject(json); // Check backend error response

       document.querySelector("#save-button p").innerText = 'Saved';
       // After successful save, clear the new key input field and re-fill the list
       document.querySelector('#new-cv-key-input').value = '';
       fillSettings(api_key); // Re-fill to update UI state from backend (includes validated keys)
    })
    .catch(e => {
       document.querySelector("#save-button p").innerText = 'Failed';
        // Improved error handling based on backend response
        e.json().then(err_data => {
            console.error("Save settings failed:", err_data); // Log full error details
            const errorResult = err_data.result || {};
            const errorKey = errorResult.key;

            if (errorKey === 'comicvine_api_keys') {
                 // Display the general CV keys error message
                 document.querySelector('#cv-keys-error').innerText = `*${err_data.error}: ${errorResult.value || 'Invalid key data'}`;
                 document.querySelector('#cv-keys-error').classList.remove('hidden');
                 // Optionally, mark specific key inputs as invalid if backend error provides detail
                 // This requires more complex logic based on backend error format
            } else if (errorKey === 'comicvine_api_url') {
                document.querySelector('#cv-url-error').innerText = `*${err_data.error}: ${errorResult.value || 'Invalid URL'}.`;
                document.querySelector('#cv-url-error').classList.remove('hidden');
                 if (cvUrlSelect && cvUrlSelect.value === 'custom') { // Check if element exists before accessing value
                    cvUrlCustomInput.classList.add('error-input');
                 }
            } else if (errorKey === 'flaresolverr_base_url') {
                 document.querySelector("#flaresolverr-input").classList.add('error-input');
            } else {
                 // For other unknown errors
                 alert(`Error saving settings: ${err_data.error || 'Unknown error'}`);
            }
        }).catch(() => {
            // Fallback for when response is not JSON or other unexpected issues
            console.error("Save settings failed (non-JSON response or parse error):", e);
            alert(`Error saving settings: Status ${e.status || 'Unknown'}`);
        });
    });
};

function generateApiKey(api_key) {
    sendAPI('POST', '/settings/api_key', api_key)
    .then(response => response.json())
    .then(json => {
       setLocalStorage({'api_key': json.result.api_key});
       document.querySelector('#api-key-display').value = json.result.api_key; // Use new ID
    });
};

// --- Add Event Listener for CV API URL Dropdown Change ---
// This listener can be attached directly as cvUrlSelect is defined outside DOMContentLoaded now
if(cvUrlSelect && cvUrlCustomInput) {
    cvUrlSelect.onchange = () => {
        if (cvUrlSelect.value === 'custom') {
            cvUrlCustomInput.classList.remove('hidden');
            cvUrlCustomInput.focus();
        } else {
            cvUrlCustomInput.classList.add('hidden');
            cvUrlCustomInput.value = ''; // Clear custom input when not selected
            cvUrlCustomInput.classList.remove('error-input'); // Clear error state
            document.querySelector('#cv-url-error').classList.add('hidden'); // Hide error message
        }
    };
} else {
    console.error("CV URL select or custom input not found outside DOMContentLoaded.");
}


// code run on load - Main entry point after DOM is ready
document.addEventListener('DOMContentLoaded', (event) => {
    console.log('DOM fully loaded and parsed. Initializing settings_general.js');

    // Get references to essential elements inside DOMContentLoaded if needed,
    // but since they are defined with `let` outside, they should be accessible.
    // We still need to check if they are null here as a safeguard.

    // --- Debugging: Check if essential elements are found and log details within DOMContentLoaded ---
    console.log("Checking essential elements within DOMContentLoaded:");
    if (!cvKeyEntryTemplate) console.error("Template Element (.pre-build-els .cv-key-entry) is NULL within DOMContentLoaded!");
    if (!cvKeysList) console.error("List Container Element (#cv-keys-list) is NULL within DOMContentLoaded!");
    if (!addCvKeyButton) console.error("Add Button Element (#add-cv-key-button) is NULL within DOMContentLoaded!");
    if (!newCvKeyInput) console.error("New Key Input Element (#new-cv-key-input) is NULL within DOMContentLoaded!");
    if (!cvUrlSelect) console.error("CV URL Select Element (#cv-url-select) is NULL within DOMContentLoaded!");
    if (!cvUrlCustomInput) console.error("CV URL Custom Input Element (#cv-url-custom-input) is NULL within DOMContentLoaded!");


    // Check if all essential elements are found
    if (!cvKeyEntryTemplate || !cvKeysList || !addCvKeyButton || !newCvKeyInput || !cvUrlSelect || !cvUrlCustomInput) {
        console.error("One or more essential elements for API key management not found. Script may not function correctly.");
        // Log detailed info again if the check fails
        console.log("Template Element (within DOMContentLoaded):", cvKeyEntryTemplate);
        console.log("List Container Element (within DOMContentLoaded):", cvKeysList);
        console.log("Add Button Element (within DOMContentLoaded):", addCvKeyButton);
        console.log("New Key Input Element (within DOMContentLoaded):", newCvKeyInput);
        console.log("CV URL Select Element (within DOMContentLoaded):", cvUrlSelect);
        console.log("CV URL Custom Input Element (within DOMContentLoaded):", cvUrlCustomInput);

        return; // Stop execution if essential elements are missing
    }
    console.log("All essential elements found within DOMContentLoaded."); // Confirm elements were found


    // Event listener for the "Add" button
    // This listener is attached inside DOMContentLoaded to ensure addCvKeyButton is available
    addCvKeyButton.onclick = () => {
       const newKey = newCvKeyInput.value.trim();
       if (newKey) {
          const existingKeys = getCvKeysFromUI();
          if (!existingKeys.includes(newKey)) {
             const newRow = createCvKeyRow(newKey); // Create a new row using the template
             if (newRow) { // Check if row creation was successful
                 cvKeysList.appendChild(newRow); // Add the new row to the list tbody
                 newCvKeyInput.value = ''; // Clear the input
                 document.querySelector('#cv-keys-error').classList.add('hidden'); // Hide error if adding successful key
             }
          } else {
             alert('API Key already exists in the list.'); // Provide feedback
          }
       } else {
            // Optional: provide feedback if the input is empty
            // newCvKeyInput.classList.add('error-input');
            // document.querySelector('#cv-keys-error').innerText = '*Please enter a key to add.';
            // document.querySelector('#cv-keys-error').classList.remove('hidden');
       }
    };

    // Event listener for the new key input field to allow adding on Enter key press
    // This listener is attached inside DOMContentLoaded
    newCvKeyInput.addEventListener('keypress', function(event) {
        // Check if the pressed key was 'Enter' (key code 13)
        if (event.key === 'Enter') {
            // Prevent the default form submission
            event.preventDefault();
            // Trigger the add button click behavior
            addCvKeyButton.click();
        }
    });


    // Initial population of settings using the API key
    // This code runs within DOMContentLoaded
    usingApiKey()
    .then(api_key => {
        fillSettings(api_key); // This will now populate the list with saved keys
        document.querySelector('#save-button').onclick = e => saveSettings(api_key);
        document.querySelector('#generate-api').onclick = e => generateApiKey(api_key);
        document.querySelector('#download-logs-button').href =
            `${url_base}/api/system/logs?api_key=${api_key}`;
    });

    // Theme toggle listener - attached inside DOMContentLoaded
    document.querySelector('#theme-input').onchange = e => {
        const value = document.querySelector('#theme-input').value;
        setLocalStorage({'theme': value});
        if (value === 'dark')
            document.querySelector(':root').classList.add('dark-mode');
        else if (value === 'light')
            document.querySelector(':root').classList.remove('dark-mode');
    };

});