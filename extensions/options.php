<?php
$root = dirname(__DIR__);
$id = defined('SIM_CONF_ID') ? SIM_CONF_ID : getenv('SIM_CONF_ID');
if (!preg_match('/\Ac[a-f0-9]{12}\z/', $id ?? '')) {
    throw new RuntimeException('Invalid simulation conference');
}
$secret = json_decode(file_get_contents($root . '/data/database.json'), true, 512, JSON_THROW_ON_ERROR);
$Opt = [
    'dbName' => 'hcsim_' . $id,
    'dbUser' => $secret['user'], 'dbPassword' => $secret['password'],
    'dbHost' => 'localhost', 'shortName' => 'Local review simulation',
    'sendEmail' => false, 'contactName' => 'Local Chair',
    'contactEmail' => 'chair@simulation.local',
    'httpAuthLogin' => true, 'disableNewUsers' => true,
    'sessionName' => 'hcsim_' . $id,
    'docstore' => $root . '/data/documents/' . $id . '/%h%x',
    'checkUpdates' => false, 'localSimulation' => true,
    'pages' => [(object) [ 'name' => 'home/simulation', 'order' => 1100,
        'print_function' => 'SimulationExtension::banner' ]]
];
require_once $root . '/upstream/src/pages/p_simulation.php';

foreach (["home", "paper", "signin", "search", "review"] as $page) {
    $Opt["pages"][] = (object) ["name" => $page . "/simulation_login", "order" => 1,
        "request_function" => "SimulationExtension::login"];
}

// A local chair is not a human PC member who needs reviewer-matching interests.
$Opt["pages"][] = (object) ["name" => "__profilecheck/pc", "merge" => true, "allow_if" => false];
