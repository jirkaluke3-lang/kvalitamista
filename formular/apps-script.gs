/**
 * KvalitaMísta – příjem zpráv z kontaktního formuláře webu.
 *
 * Kam vložit: do SOUKROMÉ Google tabulky „KvalitaMísta – zprávy z webu“
 * (Rozšíření → Apps Script). Ne do tabulky s obsahem webu – ta je veřejná!
 *
 * Nasazení: Nasadit → Nové nasazení → typ „Webová aplikace“
 *   Spustit jako: Já · Kdo má přístup: Kdokoli → Nasadit
 * Adresu webové aplikace (…/exec) vlož do tabulky obsahu webu,
 * list NASTAVENI, řádek  formular_url.
 */

const KOMU = 'dilna@informarchitekti.cz';   // kam posílat upozornění na novou zprávu

function doPost(e) {
  const p = (e && e.parameter) || {};
  if (p.web) return odpoved('ok');                       // past na roboty
  const email = (p.email || '').trim();
  const zprava = (p.zprava || '').trim();
  if (!email || !zprava || email.indexOf('@') < 1) return odpoved('chyba');

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const list = ss.getSheetByName('ZPRAVY') || ss.getSheets()[0];
  if (list.getLastRow() === 0) {
    list.appendRow(['přijato', 'jméno', 'e-mail', 'telefon', 'zpráva', 'jazyk']);
    list.setFrozenRows(1);
  }
  const jmeno = (p.jmeno || '').trim(), telefon = (p.telefon || '').trim();
  list.appendRow([new Date(), jmeno, email, telefon, zprava, p.jazyk || '']);

  MailApp.sendEmail({
    to: KOMU,
    replyTo: email,
    subject: 'KvalitaMísta – nová zpráva z webu' + (jmeno ? ' (' + jmeno + ')' : ''),
    body: zprava + '\n\n— ' + [jmeno, email, telefon].filter(String).join('\n— ')
  });
  return odpoved('ok');
}

function odpoved(text) {
  return ContentService.createTextOutput(text);
}
