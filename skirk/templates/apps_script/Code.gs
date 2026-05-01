// Skirk Apps Script relay template.
//
// This is intentionally a dumb authenticated forwarder. It should only see
// encrypted Skirk frames, never target URLs or plaintext application traffic.
//
// Script properties:
//   SKIRK_AUTH_TOKEN: shared bearer token for clients
//   SKIRK_EXIT_URL:   https://your-exit.example/tunnel

function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  const expected = props.getProperty("SKIRK_AUTH_TOKEN");
  const exitUrl = props.getProperty("SKIRK_EXIT_URL");

  if (!expected || !exitUrl) {
    return json_({ error: "server_not_configured" }, 500);
  }

  const provided = (e.parameter && e.parameter.token) || "";
  if (provided !== expected) {
    return json_({ error: "unauthorized" }, 401);
  }

  const payload = e.postData ? e.postData.contents : "";
  const response = UrlFetchApp.fetch(exitUrl, {
    method: "post",
    payload: payload,
    contentType: "application/octet-stream",
    muteHttpExceptions: true,
  });

  return ContentService
    .createTextOutput(response.getContentText())
    .setMimeType(ContentService.MimeType.TEXT);
}

function doGet() {
  return json_({ ok: true, service: "skirk-apps-script-relay" }, 200);
}

function json_(value, status) {
  return ContentService
    .createTextOutput(JSON.stringify(Object.assign({ status: status }, value)))
    .setMimeType(ContentService.MimeType.JSON);
}
