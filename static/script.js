// ---------- Login Form Submission ----------
// const loginForm = document.getElementById("login-form");
// if (loginForm) {
//   loginForm.addEventListener("submit", (e) => {
//     e.preventDefault();
//     const username = document.getElementById("username").value;
//     const password = document.getElementById("password").value; // password is the GUID here
//     localStorage.setItem("username", username);
//     localStorage.setItem("patientGuid", password);
//     window.location.href = "dashboard.html";
//   });
// }

// ---------- Fetch Patient Records for Dashboard ----------
// async function fetchPatientData() {
//   const patientGuid = localStorage.getItem("patientGuid");
//   if (!patientGuid) {
//     console.error("No patient GUID found in localStorage");
//     return;
//   }
//   try {
//     const response = await fetch("/api/patient-records", {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ guid: patientGuid })
//     });
//     if (!response.ok) {
//       throw new Error("Network response was not ok");
//     }
//     const data = await response.json();
    
//     // Personal Information
//     document.getElementById("patient-info").innerHTML = `
//       <p><strong>Name:</strong> ${data.name}</p>
//       <p><strong>Age:</strong> ${data.age}</p>
//       <p><strong>Gender:</strong> ${data.gender}</p>
//       <p><strong>Location:</strong> ${data.location}</p>`;
    
//     // Medical Conditions
//     document.getElementById("medical-history").innerHTML = data.conditions
//       .map((c) => `<p>${c}</p>`)
//       .join("");
    
//     // Medications
//     document.getElementById("medications").innerHTML = data.medications
//       .map((m) => `<p><strong>${m.name}</strong> - ${m.dosage} (${m.schedule})</p>`)
//       .join("");
    
//     // Activity Log
//     document.getElementById("activity-log").innerHTML = data.activity_log
//       .map((a) => `<p>${a.date}: ${a.activity} for ${a.duration}</p>`)
//       .join("");
    
//     // Alerts
//     document.getElementById("alerts").innerHTML = data.alerts
//       .map((a) => `<p>${new Date(a.timestamp).toLocaleString()}: ${a.message}</p>`)
//       .join("");
    
//     // Optionally, populate #health-metrics if available
//   } catch (error) {
//     console.error("Error fetching patient data:", error);
//   }
// }
// if (document.getElementById("patient-info")) {
//   fetchPatientData(); // Only run on dashboard.html
//}

// ---------- Chatbot Interactions for Maya Page ----------
// const chatBox = document.getElementById("chat-box");
// const chatInput = document.getElementById("chat-input");
// const sendBtn = document.getElementById("send-btn");

// async function sendMessage() {
//   const message = chatInput.value.trim();
//   if (!message) return;
//   if (chatBox) {
//     // Display user's message
//     chatBox.innerHTML += `<p><strong>You:</strong> ${message}</p>`;
//   }

//   // Retrieve patientGuid
//   const patientGuid = localStorage.getItem("patientGuid");

//   try {
//     const response = await fetch("/api/chatbot", {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ message, patientGuid })
//     });
//     const data = await response.json();
//     if (chatBox) {
//       chatBox.innerHTML += `<p><strong>Maya:</strong> ${data.reply}</p>`;
//     }
//   } catch (error) {
//     console.error("Error communicating with chatbot:", error);
//   }
//   if (chatInput) chatInput.value = "";
// }

// if (sendBtn && chatInput) {
//   sendBtn.addEventListener("click", sendMessage);
//   chatInput.addEventListener("keypress", (e) => {
//     if (e.key === "Enter") sendMessage();
//   });
// }