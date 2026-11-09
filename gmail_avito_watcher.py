#!/usr/bin/env python3
"""Forward Avito alert emails from Gmail to Telegram using IMAP/TLS."""
import email, imaplib, os, re, time, html, json, urllib.request
from email.header import decode_header, make_header
from email.utils import parseaddr
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
GMAIL_USER=os.getenv('GMAIL_USER','').strip()
GMAIL_APP_PASSWORD=os.getenv('GMAIL_APP_PASSWORD','').replace(' ','').strip()
BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
CHAT_ID=os.getenv('TELEGRAM_CHAT_ID','').strip()
POLL_SECONDS=int(os.getenv('GMAIL_POLL_SECONDS','60'))
def decode(value):
    try: return str(make_header(decode_header(value or '')))
    except Exception: return value or ''
def body_text(msg):
    chunks=[]
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() not in ('text/plain','text/html'): continue
        raw=part.get_payload(decode=True)
        if raw: chunks.append(raw.decode(part.get_content_charset() or 'utf-8',errors='replace'))
    return '\n'.join(chunks)
def avito_link(text):
    text=html.unescape(text)
    for url in re.findall(r'https?://[^\s"\'<>]+',text,flags=re.I):
        url=url.rstrip(').,;]')
        if 'avito.ru/' in url.lower(): return url
    return ''
def send_telegram(text):
    url=f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload=json.dumps({'chat_id':CHAT_ID,'text':text,'parse_mode':'HTML'}).encode()
    req=urllib.request.Request(url,data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r:
        result=json.loads(r.read().decode())
        if not result.get('ok'): raise RuntimeError(str(result))
def check_mail():
    box=imaplib.IMAP4_SSL('imap.gmail.com',993)
    box.login(GMAIL_USER,GMAIL_APP_PASSWORD)
    box.select('INBOX')
    status,data=box.search(None,'UNSEEN')
    sent=0
    if status=='OK':
        for uid in data[0].split():
            status,items=box.fetch(uid,'(RFC822)')
            if status!='OK' or not items or not isinstance(items[0],tuple): continue
            msg=email.message_from_bytes(items[0][1])
            name,address=parseaddr(msg.get('From',''))
            subject=decode(msg.get('Subject','(без темы)')).replace('\n',' ').strip()
            url=avito_link(body_text(msg))
            if 'avito' not in (name+' '+address).lower() and not url: continue
            if not url: continue
            text=('🎯 <b>Новое письмо с Avito</b>\n\n'
                  f'<b>{html.escape(subject[:400])}</b>\n'
                  f'Отправитель: {html.escape(address or name or "не указан")}\n\n'
                  f'<a href="{html.escape(url,quote=True)}">Открыть объявление на Avito</a>')
            send_telegram(text)
            box.store(uid,'+FLAGS','\\Seen')
            sent+=1
    box.logout()
    return sent
def main():
    missing=[k for k,v in {'GMAIL_USER':GMAIL_USER,'GMAIL_APP_PASSWORD':GMAIL_APP_PASSWORD,'TELEGRAM_BOT_TOKEN':BOT_TOKEN,'TELEGRAM_CHAT_ID':CHAT_ID}.items() if not v]
    if missing: raise SystemExit('Заполни в .env: '+', '.join(missing))
    print(f'Gmail → Telegram запущен; проверка каждые {POLL_SECONDS} сек.')
    while True:
        try:
            n=check_mail()
            if n: print('Отправлено уведомлений:',n)
        except KeyboardInterrupt:
            print('Остановлено.'); break
        except Exception as exc:
            print('Ошибка IMAP/Telegram:',repr(exc))
        time.sleep(POLL_SECONDS)
if __name__=='__main__': main()
