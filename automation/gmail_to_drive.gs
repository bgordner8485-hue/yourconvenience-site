/**
 * @YourConvenience — files PA Lottery report emails into Drive so the website can read them.
 *
 * Install once, in the Google account that receives the reports:
 *   1. script.google.com → New project → paste this in → save as "Lottery reports to Drive"
 *   2. Run setUp() once and approve the permissions it asks for
 * It creates the reports folder itself, shares it with the website's reader account, and logs the folder id.
 * After that it checks every 15 minutes on its own.
 *
 * It labels handled mail "Lottery/Filed" so nothing is processed twice, and it never deletes anything.
 */
var REPORTS_FOLDER_NAME = '15_Lottery_Reports';   // created in My Drive on first run
var SERVICE_ACCOUNT = 'store-bot@yourconvenience-site.iam.gserviceaccount.com';  // the website's reader
var SEARCH = 'from:(palottery.pa.gov OR lottery.pa.gov OR paretailer.lottery.state.pa.us) has:attachment -label:Lottery/Filed newer_than:14d';

function setUp() {
  var folder = getFolder();
  try { folder.addViewer(SERVICE_ACCOUNT); } catch (e) { console.log('Share note: ' + e); }
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('fileReports').timeBased().everyMinutes(15).create();
  console.log('REPORTS FOLDER ID: ' + folder.getId());
  fileReports();
}

function getFolder() {
  var it = DriveApp.getFoldersByName(REPORTS_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(REPORTS_FOLDER_NAME);
}

function fileReports() {
  var folder = getFolder();
  var label = GmailApp.getUserLabelByName('Lottery/Filed') || GmailApp.createLabel('Lottery/Filed');
  var threads = GmailApp.search(SEARCH, 0, 25);
  threads.forEach(function (thread) {
    thread.getMessages().forEach(function (msg) {
      var stamp = Utilities.formatDate(msg.getDate(), 'America/New_York', 'yyyy-MM-dd');
      msg.getAttachments().forEach(function (att) {
        var name = att.getName();
        if (/\.(csv|xlsx?|pdf|txt|rpt)$/i.test(name)) {
          folder.createFile(att.copyBlob().setName(stamp + ' ' + name));
        }
      });
      // reports that arrive as plain text in the body get saved too
      if (msg.getAttachments().length === 0 && /winning numbers|payout|prizes/i.test(msg.getSubject())) {
        folder.createFile(Utilities.newBlob(msg.getPlainBody(), 'text/plain',
          stamp + ' ' + msg.getSubject().replace(/[\\/:*?"<>|]/g, '-') + '.txt'));
      }
    });
    thread.addLabel(label);
  });
  console.log('Filed ' + threads.length + ' thread(s)');
}
