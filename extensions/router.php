<?php
// This server is private to the loopback Python proxy. Never expose it directly.
$root = dirname(__DIR__);
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (!preg_match('~^/c/(c[a-f0-9]{12})(/.*)?$~', $path, $m)) {
    http_response_code(404); exit('Not found');
}
$secret = trim(file_get_contents($root . '/data/proxy-key'));
if (!hash_equals($secret, $_SERVER['HTTP_X_SIM_PROXY'] ?? '')) {
    http_response_code(403); exit('Local proxy required');
}
define('SIM_CONF_ID', $m[1]);
define('HOTCRP_OPTIONS', $root . '/extensions/options.php');
$_SERVER['REMOTE_USER'] = 'chair@simulation.local';
$_SERVER['SCRIPT_NAME'] = '/c/' . $m[1] . '/index.php';
$_SERVER['PHP_SELF'] = $_SERVER['SCRIPT_NAME'];
$_SERVER['SCRIPT_FILENAME'] = $root . '/upstream/index.php';
chdir($root . '/upstream');
require 'index.php';
