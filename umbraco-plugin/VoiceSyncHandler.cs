using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Umbraco.Cms.Core.Events;
using Umbraco.Cms.Core.Notifications;
using Umbraco.Cms.Core.Services;
using Umbraco.Extensions;

namespace Umbraco.Plugin.VoiceSync
{
    public class GenerateResponse
    {
        [System.Text.Json.Serialization.JsonPropertyName("task_id")]
        public string TaskId { get; set; } = string.Empty;

        [System.Text.Json.Serialization.JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;
    }

    public class VoiceSyncHandler : INotificationHandler<ContentPublishedNotification>
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IContentService _contentService;
        private readonly IConfiguration _configuration;

        public VoiceSyncHandler(
            IHttpClientFactory httpClientFactory,
            IContentService contentService,
            IConfiguration configuration)
        {
            _httpClientFactory = httpClientFactory;
            _contentService = contentService;
            _configuration = configuration;
        }

        public void Handle(ContentPublishedNotification notification)
        {
            foreach (var content in notification.PublishedEntities)
            {
                // Ensure the content type has the required properties
                if (!content.HasProperty("voiceSyncAudioUrl") || 
                    !content.HasProperty("voiceSyncTaskId") || 
                    !content.HasProperty("bodyText"))
                {
                    continue;
                }

                var audioUrl = content.GetValue<string>("voiceSyncAudioUrl");
                var taskId = content.GetValue<string>("voiceSyncTaskId");

                // Skip if audio is already generated or task is in progress
                if (!string.IsNullOrEmpty(audioUrl) || !string.IsNullOrEmpty(taskId))
                {
                    continue;
                }

                var bodyText = content.GetValue<string>("bodyText");
                if (string.IsNullOrEmpty(bodyText) || bodyText.Length < 10)
                {
                    continue;
                }

                // Strip HTML tags and limit length to 5000 characters
                string cleanText = StripHtml(bodyText);
                if (cleanText.Length > 5000)
                {
                    cleanText = cleanText.Substring(0, 5000);
                }

                if (cleanText.Length < 10)
                {
                    continue;
                }

                try
                {
                    // Trigger the background TTS generation task on our FastAPI server
                    var generatedTaskId = TriggerTtsGeneration(cleanText).GetAwaiter().GetResult();
                    if (!string.IsNullOrEmpty(generatedTaskId))
                    {
                        content.SetValue("voiceSyncTaskId", generatedTaskId);
                        _contentService.Save(content);
                    }
                }
                catch (Exception)
                {
                    // Fail silently in pipeline to prevent publishing from blocking completely
                }
            }
        }

        private async Task<string> TriggerTtsGeneration(string text)
        {
            var apiUrl = _configuration["VoiceSync:ApiUrl"] ?? "http://localhost:8000";
            var apiKey = _configuration["VoiceSync:ApiKey"];
            var voiceId = _configuration["VoiceSync:VoiceId"] ?? "default";

            using var client = _httpClientFactory.CreateClient();
            client.BaseAddress = new Uri(apiUrl);
            
            if (!string.IsNullOrEmpty(apiKey))
            {
                client.DefaultRequestHeaders.Add("X-API-Key", apiKey);
            }

            var requestBody = new
            {
                text = text,
                voice_id = voiceId,
                language = "tr"
            };

            var response = await client.PostAsJsonAsync("/generate", requestBody);
            if (response.IsSuccessStatusCode)
            {
                var result = await response.Content.ReadFromJsonAsync<GenerateResponse>();
                return result?.TaskId;
            }

            return null;
        }

        private string StripHtml(string input)
        {
            if (string.IsNullOrEmpty(input)) return string.Empty;
            
            // Decode HTML entities
            var clean = WebUtility.HtmlDecode(input);
            
            // Remove HTML tags
            return Regex.Replace(clean, "<.*?>", string.Empty).Trim();
        }
    }
}
