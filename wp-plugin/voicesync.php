<?php
/*
Plugin Name: VoiceSync
Description: Blog yazılarını klonlanmış sesle okur. Async, cache'li.
Version: 2.0.0
Author: VoiceSync Team
License: GPL2
*/

// Prevent direct access
defined('ABSPATH') || exit;

/**
 * Get the API URL from Settings.
 *
 * @return string
 */
function vs_api() {
    return get_option('vs_api_url', 'http://localhost:8000');
}

/**
 * Get the API Key from Settings.
 *
 * @return string
 */
function vs_key() {
    return get_option('vs_api_key', '');
}

/**
 * Get the Voice ID from Settings.
 *
 * @return string
 */
function vs_voice() {
    return get_option('vs_voice_id', 'default');
}

/**
 * Build request headers for communicating with FastAPI.
 *
 * @return array
 */
function vs_headers() {
    return array(
        'Content-Type' => 'application/json',
        'X-API-Key'    => vs_key(),
    );
}

/**
 * Action triggered when a post is published.
 * Triggers an asynchronous generation task on the FastAPI backend.
 *
 * @param int     $post_id Post ID.
 * @param WP_Post $post    Post object.
 */
add_action('publish_post', 'vs_start_job', 10, 2);
function vs_start_job($post_id, $post) {
    // Stop if we already have a generated audio URL or a running task
    if (get_post_meta($post_id, '_vs_audio_url', true) || get_post_meta($post_id, '_vs_task_id', true)) {
        return;
    }

    // Strip tags and grab the first 5000 characters
    $content = wp_strip_all_tags($post->post_content);
    $text = mb_substr($content, 0, 5000, 'UTF-8');
    
    if (empty(trim($text))) {
        return;
    }

    $api_url = rtrim(vs_api(), '/') . '/generate';
    
    $body = array(
        'text'     => $text,
        'voice_id' => vs_voice(),
        'language' => 'tr',
    );

    // Call the /generate endpoint asynchronously (with a reasonable timeout)
    $response = wp_remote_post($api_url, array(
        'headers'     => vs_headers(),
        'body'        => json_encode($body),
        'data_format' => 'body',
        'timeout'     => 15,
    ));

    if (is_wp_error($response)) {
        return;
    }

    $response_code = wp_remote_retrieve_response_code($response);
    if ($response_code !== 202) {
        return;
    }

    $response_body = json_decode(wp_remote_retrieve_body($response), true);
    if (isset($response_body['task_id'])) {
        $task_id = $response_body['task_id'];
        
        // Save task_id to post meta
        update_post_meta($post_id, '_vs_task_id', $task_id);

        // Schedule first cron check in 30 seconds
        wp_schedule_single_event(time() + 30, 'vs_poll_job', array($post_id));
    }
}

/**
 * Cron action to poll the FastAPI task status.
 *
 * @param int $post_id Post ID.
 */
add_action('vs_poll_job', 'vs_check_job');
function vs_check_job($post_id) {
    $task_id = get_post_meta($post_id, '_vs_task_id', true);
    if (!$task_id) {
        return;
    }

    $api_url = rtrim(vs_api(), '/') . '/status/' . urlencode($task_id);

    $response = wp_remote_get($api_url, array(
        'headers' => vs_headers(),
        'timeout' => 15,
    ));

    if (is_wp_error($response)) {
        // Retry in 60 seconds if HTTP request fails temporarily
        wp_schedule_single_event(time() + 60, 'vs_poll_job', array($post_id));
        return;
    }

    $response_code = wp_remote_retrieve_response_code($response);
    if ($response_code !== 200) {
        // Clean up task if API returns an error status code to avoid infinite loops
        delete_post_meta($post_id, '_vs_task_id');
        return;
    }

    $response_body = json_decode(wp_remote_retrieve_body($response), true);
    $status = isset($response_body['status']) ? $response_body['status'] : 'error';

    if ($status === 'done' && isset($response_body['audio_url'])) {
        // Construct the full audio URL using vs_api() base URL
        $audio_relative = $response_body['audio_url'];
        $full_audio_url = rtrim(vs_api(), '/') . '/' . ltrim($audio_relative, '/');
        
        update_post_meta($post_id, '_vs_audio_url', $full_audio_url);
        delete_post_meta($post_id, '_vs_task_id');
    } elseif (strpos($status, 'error') === 0 || $status === 'failed') {
        // Job failed on the backend, clean up
        delete_post_meta($post_id, '_vs_task_id');
    } else {
        // Job is still processing, schedule next poll in 60 seconds
        wp_schedule_single_event(time() + 60, 'vs_poll_job', array($post_id));
    }
}

/**
 * Filter the content of singular blog posts to inject the audio player.
 *
 * @param string $content Post content.
 * @return string
 */
add_filter('the_content', 'vs_inject_player');
function vs_inject_player($content) {
    if (is_single()) {
        $post_id = get_the_ID();
        $audio_url = get_post_meta($post_id, '_vs_audio_url', true);
        
        if ($audio_url) {
            $player_html = '
            <div class="voicesync-player" data-src="' . esc_url($audio_url) . '">
                <button class="vs-play-btn" onclick="vsToggle(this)">▶ Yazıyı Dinle</button>
                <span class="vs-time">0:00</span>
                <audio class="vs-audio-element" preload="none"></audio>
            </div>';
            $content = $player_html . $content;
        }
    }
    return $content;
}

/**
 * Enqueue scripts and styles for the frontend audio player.
 */
add_action('wp_enqueue_scripts', 'vs_enqueue_assets');
function vs_enqueue_assets() {
    wp_enqueue_style('voicesync-player-style', plugins_url('player.css', __FILE__), array(), '2.0.0');
    wp_enqueue_script('voicesync-player-script', plugins_url('player.js', __FILE__), array(), '2.0.0', true);
}

/**
 * Add options page under Settings menu.
 */
add_action('admin_menu', 'vs_add_admin_menu');
function vs_add_admin_menu() {
    add_options_page(
        'VoiceSync Ayarları',
        'VoiceSync',
        'manage_options',
        'voicesync-settings',
        'vs_render_settings_page'
    );
}

/**
 * Render Settings Page markup and process form submissions.
 */
function vs_render_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }

    if (isset($_POST['vs_submit_settings'])) {
        check_admin_referer('vs_settings_nonce');

        $api_url  = isset($_POST['vs_api_url']) ? esc_url_raw(trim($_POST['vs_api_url'])) : '';
        $api_key  = isset($_POST['vs_api_key']) ? sanitize_text_field(trim($_POST['vs_api_key'])) : '';
        $voice_id = isset($_POST['vs_voice_id']) ? sanitize_text_field(trim($_POST['vs_voice_id'])) : '';

        update_option('vs_api_url', $api_url);
        update_option('vs_api_key', $api_key);
        update_option('vs_voice_id', $voice_id);

        echo '<div class="updated"><p>Ayarlar başarıyla kaydedildi.</p></div>';
    }

    $api_url  = vs_api();
    $api_key  = vs_key();
    $voice_id = vs_voice();
    ?>
    <div class="wrap">
        <h1>VoiceSync Ayarları</h1>
        <form method="post" action="">
            <?php wp_nonce_field('vs_settings_nonce'); ?>
            <table class="form-table">
                <tr valign="top">
                    <th scope="row">API URL</th>
                    <td>
                        <input type="text" name="vs_api_url" value="<?php echo esc_attr($api_url); ?>" class="regular-text" />
                        <p class="description">FastAPI sunucunuzun adresi (örn: http://localhost:8000).</p>
                    </td>
                </tr>
                <tr valign="top">
                    <th scope="row">API Key</th>
                    <td>
                        <input type="password" name="vs_api_key" value="<?php echo esc_attr($api_key); ?>" class="regular-text" />
                        <p class="description">FastAPI backend kimlik doğrulaması için gereken API Key.</p>
                    </td>
                </tr>
                <tr valign="top">
                    <th scope="row">Ses ID (Voice ID)</th>
                    <td>
                        <input type="text" name="vs_voice_id" value="<?php echo esc_attr($voice_id); ?>" class="regular-text" />
                        <p class="description">Ses klonlamada referans alınacak ses ID'si (varsayılan: default).</p>
                    </td>
                </tr>
            </table>
            <input type="submit" name="vs_submit_settings" class="button button-primary" value="Ayarları Kaydet" />
        </form>
    </div>
    <?php
}
