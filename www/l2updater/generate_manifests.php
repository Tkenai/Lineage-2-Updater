<?php
/**
 * Gera fullcheck.json e update_json_url.json
 * com base no conteúdo da pasta client/.
 *
 * Uso (linha de comando):
 *   php generate_manifests.php --base-url="http://192.168.15.57:8080/l2updater/client"
 */

ini_set('display_errors', 1);
error_reporting(E_ALL);

// -------------------- PARÂMETROS --------------------

// base_url padrão (pode sobrescrever via --base-url=)
$baseUrl = "http://192.168.15.57:8080/l2updater/client";

// lê argumentos da linha de comando
foreach ($argv as $arg) {
    if (strpos($arg, '--base-url=') === 0) {
        $baseUrl = substr($arg, strlen('--base-url='));
    }
}

// diretórios base
$rootDir   = __DIR__;                  // www/l2updater
$clientDir = $rootDir . DIRECTORY_SEPARATOR . 'client';

// arquivos de saída
$fullcheckFile      = $rootDir . DIRECTORY_SEPARATOR . 'fullcheck.json';
$updateJsonUrlFile  = $rootDir . DIRECTORY_SEPARATOR . 'update_json_url.json';

// valida pasta client
if (!is_dir($clientDir)) {
    fwrite(STDERR, "ERRO: pasta 'client' não encontrada em: {$clientDir}" . PHP_EOL);
    exit(1);
}

// -------------------- FUNÇÕES AUXILIARES --------------------

function encodeUrlPath($relativePath)
{
    $segments = explode('/', $relativePath);
    $segments = array_map('rawurlencode', $segments);
    return implode('/', $segments);
}

/**
 * Converte caminho absoluto em caminho relativo a partir de $clientDir
 * com separadores '/' (estilo URL).
 */
function makeRelativePath($absolutePath, $clientDir)
{
    $clientDir = rtrim($clientDir, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;

    // normaliza para o sistema atual
    $abs = realpath($absolutePath);
    $base = realpath($clientDir);

    if ($abs === false || $base === false) {
        return null;
    }

    if (strpos($abs, $base) !== 0) {
        return null;
    }

    $relative = substr($abs, strlen($base));

    // converte separadores para '/'
    return str_replace(DIRECTORY_SEPARATOR, '/', $relative);
}

/**
 * Retorna true se o arquivo deve ser ignorado no JSON.
 * (ex.: este script, .git, .DS_Store, etc)
 */
function shouldIgnore($relativePath)
{
    $relativePath = ltrim($relativePath, '/');

    if ($relativePath === '') {
        return true;
    }

    // ignora diretórios de controle de versão e arquivos temporários
    $ignorePrefixes = [
        '.git/',
        '.svn/',
    ];

    $ignoreFiles = [
        '.DS_Store',
        'Thumbs.db',
        'web.config',
    ];

    foreach ($ignorePrefixes as $prefix) {
        if (strpos($relativePath, $prefix) === 0) {
            return true;
        }
    }

    if (in_array(basename($relativePath), $ignoreFiles, true)) {
        return true;
    }

    return false;
}

// -------------------- VARREDURA DA PASTA CLIENT --------------------

$allFiles      = []; // para fullcheck.json
$systemEnFiles = []; // para update_json_url.json

$iterator = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator($clientDir, FilesystemIterator::SKIP_DOTS),
    RecursiveIteratorIterator::SELF_FIRST
);

foreach ($iterator as $fileInfo) {
    if (!$fileInfo->isFile()) {
        continue;
    }

    $absolutePath = $fileInfo->getPathname();
    $relativePath = makeRelativePath($absolutePath, $clientDir);

    if ($relativePath === null) {
        continue;
    }

    if (shouldIgnore($relativePath)) {
        continue;
    }

    // calcula hash e size
    $sha1 = sha1_file($absolutePath);
    if ($sha1 === false) {
        fwrite(STDERR, "Aviso: não foi possível calcular SHA1 de {$absolutePath}" . PHP_EOL);
        continue;
    }

    // tamanho em BYTES (se quiser em KB, ver comentário logo abaixo)
    $sizeBytes = filesize($absolutePath);
    if ($sizeBytes === false) {
        $sizeBytes = 0;
    }

    // se quiser em KB (arredondado pra cima), descomente:
    // $sizeKb = (int) ceil($sizeBytes / 1024);
    // e use $sizeKb em vez de $sizeBytes na estrutura abaixo.

    $urlPath = encodeUrlPath($relativePath);

    $entry = [
        'path' => $relativePath,
        'url'  => $baseUrl . $urlPath,
        'sha1' => strtoupper($sha1),
        'size' => $sizeBytes,
    ];

    // adiciona em fullcheck (todos os arquivos)
    $allFiles[] = $entry;

    // adiciona em update_json_url.json apenas se começa com system_en/
    if (strpos($relativePath, '/system_en/') === 0) {
        $systemEnFiles[] = $entry;
    }
}

// -------------------- MONTAGEM DOS JSONS --------------------

$fullcheckData = [
    'base_url' => $baseUrl,
    'files'    => $allFiles,
];

$updateJsonUrlData = [
    'base_url' => $baseUrl,
    'files'    => $systemEnFiles,
];

// -------------------- GRAVAÇÃO DOS ARQUIVOS --------------------

file_put_contents(
    $fullcheckFile,
    json_encode($fullcheckData, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
);

file_put_contents(
    $updateJsonUrlFile,
    json_encode($updateJsonUrlData, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
);

echo "Arquivos gerados com sucesso:" . PHP_EOL;
echo " - {$fullcheckFile}" . PHP_EOL;
echo " - {$updateJsonUrlFile}" . PHP_EOL;
