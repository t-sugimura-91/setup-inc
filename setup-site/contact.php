<?php
declare(strict_types=1);

/* ------------------------------------------------------------------
   SET UP お問い合わせフォーム 受信スクリプト

   外部サービス（FormSubmit等）を経由せず、このサーバー内で完結して
   メールを送信します。個人情報がサーバーの外に出ません。
   ------------------------------------------------------------------ */

/* ===== 設定 ==================================================== */
const MAIL_TO        = 't.sugimura@setup-inc.com';            // 受信先
const MAIL_FROM      = 'noreply@setup-inc.com';               // 送信元（必ずこのドメインのアドレスに）
const SITE_NAME      = 'SET UP';
const THANKS_URL     = 'https://setup-inc.com/thanks.html';
const FORM_URL       = 'https://setup-inc.com/contact.html';
const ALLOWED_HOST   = 'setup-inc.com';
const RATE_SECONDS   = 15;      // 同一IPからの連続送信の最短間隔（秒）
const SEND_AUTOREPLY = true;    // 送信者への自動返信（不要なら false）
/* =============================================================== */

date_default_timezone_set('Asia/Tokyo');
mb_language('uni');
mb_internal_encoding('UTF-8');

/* ---------- 共通処理 ---------- */

function bail(string $message, int $status = 400): void {
    http_response_code($status);
    header('Content-Type: text/html; charset=UTF-8');
    $m = htmlspecialchars($message, ENT_QUOTES, 'UTF-8');
    echo <<<HTML
<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>送信できませんでした｜SET UP</title>
<style>
  body{margin:0; padding:12vh 22px; background:#fff; color:#14203A; line-height:1.95;
       font-family:"Zen Kaku Gothic New",system-ui,sans-serif;}
  .b{max-width:520px; margin:0 auto;}
  h1{font-family:"Shippori Mincho B1",serif; font-size:24px; color:#091E41; margin:0 0 20px;}
  p{font-size:15px; color:#616B80; margin:0 0 1.4em;}
  a{display:inline-block; margin-top:14px; font-size:14px; color:#091E41; text-decoration:none;
    border:1px solid #091E41; padding:13px 26px; border-radius:2px;}
</style></head>
<body><div class="b">
<h1>送信できませんでした</h1>
<p>{$m}</p>
<p>お手数ですが、入力内容をご確認のうえ、もう一度お試しください。</p>
<a href="/contact.html">フォームに戻る</a>
</div></body></html>
HTML;
    exit;
}

/** ヘッダーインジェクション対策：改行とNULを除去 */
function clean(string $v): string {
    return trim(str_replace(["\r", "\n", "\0"], '', $v));
}

function field(string $name): string {
    $v = $_POST[$name] ?? '';
    return is_string($v) ? trim($v) : '';
}

/* ---------- 受け付ける条件 ---------- */

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Location: ' . FORM_URL, true, 303);
    exit;
}

// 他サイトからの踏み台利用を防ぐ（Refererが付いている場合のみ検査）
$ref = $_SERVER['HTTP_REFERER'] ?? '';
if ($ref !== '') {
    $host = (string)(parse_url($ref, PHP_URL_HOST) ?? '');
    if ($host !== ALLOWED_HOST && $host !== 'www.' . ALLOWED_HOST) {
        bail('不正な送信元からのリクエストです。');
    }
}

// ハニーポット：値が入っていればボットとみなし、成功を装って破棄する
if (field('_honey') !== '') {
    header('Location: ' . THANKS_URL, true, 303);
    exit;
}

// 連続送信の抑制（IPは平文で保存せずハッシュ化）
$lockFile = sys_get_temp_dir() . '/setup_form_' . hash('sha256', (string)($_SERVER['REMOTE_ADDR'] ?? ''));
if (is_file($lockFile) && (time() - (int)filemtime($lockFile)) < RATE_SECONDS) {
    bail('送信の間隔が短すぎます。しばらく時間をおいてからお試しください。', 429);
}
@touch($lockFile);

/* ---------- 入力の検証 ---------- */

$company = field('会社名');
$name    = field('お名前');
$email   = field('メールアドレス');
$tel     = field('電話番号');
$type    = field('ご相談の種類');
$budget  = field('月間広告費');
$message = field('ご相談内容');

if ($name === '' || $email === '' || $type === '' || $message === '') {
    bail('必須項目が入力されていません。');
}
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    bail('メールアドレスの形式が正しくありません。');
}
if (mb_strlen($name) > 100 || mb_strlen($message) > 5000) {
    bail('入力された文字数が上限を超えています。');
}

/* ---------- 本文の組み立て ---------- */

$subject = clean(field('_subject'));
if ($subject === '' || mb_strlen($subject) > 120) {
    $subject = '【' . SITE_NAME . '】サイトからのお問い合わせ';
}

$rows = [
    '会社名・屋号'   => $company,
    'お名前'         => $name,
    'メールアドレス' => $email,
    '電話番号'       => $tel,
    'ご相談の種類'   => $type,
    '月間広告費'     => $budget,
];

$line = str_repeat('-', 46);
$body = "サイトのお問い合わせフォームから送信がありました。\n{$line}\n\n";
foreach ($rows as $k => $v) {
    $body .= $k . '：' . ($v !== '' ? $v : '（未記入）') . "\n";
}
$body .= "\nご相談内容：\n" . $message . "\n\n";
$body .= "{$line}\n";
$body .= '送信日時：' . date('Y年n月j日 H:i:s') . "\n";
$body .= '送信元IP：' . ($_SERVER['REMOTE_ADDR'] ?? '不明') . "\n";

/* ---------- 送信 ---------- */

$fromName = mb_encode_mimeheader(SITE_NAME, 'UTF-8');
$replyTo  = mb_encode_mimeheader(clean($name), 'UTF-8') . ' <' . clean($email) . '>';

$headers  = 'From: ' . $fromName . ' <' . MAIL_FROM . ">\r\n";
$headers .= 'Reply-To: ' . $replyTo . "\r\n";
$headers .= "X-Mailer: SET UP contact form\r\n";

if (!mb_send_mail(MAIL_TO, $subject, $body, $headers, '-f' . MAIL_FROM)) {
    bail('メールの送信に失敗しました。時間をおいて再度お試しください。', 500);
}

/* ---------- 送信者への自動返信 ---------- */

if (SEND_AUTOREPLY) {
    $rSubject = '【' . SITE_NAME . '】お問い合わせを受け付けました';
    $rBody  = clean($name) . " 様\n\n";
    $rBody .= "お問い合わせいただき、ありがとうございます。\n";
    $rBody .= "以下の内容で承りました。内容を確認のうえ、2営業日以内にご返信します。\n\n";
    $rBody .= "{$line}\n\n";
    foreach ($rows as $k => $v) {
        $rBody .= $k . '：' . ($v !== '' ? $v : '（未記入）') . "\n";
    }
    $rBody .= "\nご相談内容：\n" . $message . "\n\n";
    $rBody .= "{$line}\n\n";
    $rBody .= "※ このメールは自動送信です。ご返信いただいても確認できません。\n";
    $rBody .= "　 お急ぎの場合は、このメールに記載の内容を添えて改めてフォームよりご連絡ください。\n\n";
    $rBody .= SITE_NAME . "\n" . FORM_URL . "\n";

    $rHeaders  = 'From: ' . $fromName . ' <' . MAIL_FROM . ">\r\n";
    $rHeaders .= 'Reply-To: ' . $fromName . ' <' . MAIL_TO . ">\r\n";
    $rHeaders .= "Auto-Submitted: auto-replied\r\n";
    $rHeaders .= "X-Mailer: SET UP contact form\r\n";

    @mb_send_mail(clean($email), $rSubject, $rBody, $rHeaders, '-f' . MAIL_FROM);
}

header('Location: ' . THANKS_URL, true, 303);
exit;
