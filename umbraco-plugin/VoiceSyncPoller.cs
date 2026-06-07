using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Umbraco.Cms.Core.Models;
using Umbraco.Cms.Core.Services;

namespace Umbraco.Plugin.VoiceSync
{
    public class StatusResponse
    {
        [System.Text.Json.Serialization.JsonPropertyName("task_id")]
        public string TaskId { get; set; } = string.Empty;

        [System.Text.Json.Serialization.JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [System.Text.Json.Serialization.JsonPropertyName("audio_url")]
        public string AudioUrl { get; set; } = string.Empty;
    }

    public class VoiceSyncPoller : BackgroundService
    {
        private readonly IServiceProvider _serviceProvider;
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IConfiguration _configuration;

        public VoiceSyncPoller(
            IServiceProvider serviceProvider,
            IHttpClientFactory httpClientFactory,
            IConfiguration configuration)
        {
            _serviceProvider = serviceProvider;
            _httpClientFactory = httpClientFactory;
            _configuration = configuration;
        }

        protected override async Task ExecuteAsync(CancellationToken stoppingToken)
        {
            // Background polling loop
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    // Create a scope for thread-safe DI resolving of transient/scoped services like IContentService
                    using (var scope = _serviceProvider.CreateScope())
                    {
                        var contentService = scope.ServiceProvider.GetRequiredService<IContentService>();
                        await PollPendingTasksAsync(contentService, stoppingToken);
                    }
                }
                catch (Exception)
                {
                    // Prevent background thread failure from crashing the app pool
                }

                // Poll every 30 seconds
                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
            }
        }

        private async Task PollPendingTasksAsync(IContentService contentService, CancellationToken ct)
        {
            var rootNodes = contentService.GetRootContent();
            foreach (var root in rootNodes)
            {
                if (ct.IsCancellationRequested) return;
                await CheckAndProcessContentAsync(contentService, root, ct);

                long totalRecords;
                int pageIndex = 0;
                const int pageSize = 100;

                // Page through descendants recursively to find items with pending task IDs
                do
                {
                    if (ct.IsCancellationRequested) return;
                    var descendants = contentService.GetPagedDescendants(root.Id, pageIndex, pageSize, out totalRecords);
                    
                    foreach (var desc in descendants)
                    {
                        if (ct.IsCancellationRequested) return;
                        await CheckAndProcessContentAsync(contentService, desc, ct);
                    }
                    
                    pageIndex++;
                } while (pageIndex * pageSize < totalRecords);
            }
        }

        private async Task CheckAndProcessContentAsync(IContentService contentService, IContent content, CancellationToken ct)
        {
            if (!content.HasProperty("voiceSyncTaskId") || !content.HasProperty("voiceSyncAudioUrl"))
            {
                return;
            }

            var taskId = content.GetValue<string>("voiceSyncTaskId");
            if (string.IsNullOrEmpty(taskId))
            {
                return;
            }

            // Query the FastAPI backend status
            var statusResponse = await CheckTaskStatusAsync(taskId, ct);
            if (statusResponse == null)
            {
                return; // Server unresponsive, will retry in next loop
            }

            if (statusResponse.Status == "done" && !string.IsNullOrEmpty(statusResponse.AudioUrl))
            {
                var apiUrl = _configuration["VoiceSync:ApiUrl"] ?? "http://localhost:8000";
                var fullAudioUrl = $"{apiUrl.TrimEnd('/')}/{statusResponse.AudioUrl.TrimStart('/')}";

                content.SetValue("voiceSyncAudioUrl", fullAudioUrl);
                content.SetValue("voiceSyncTaskId", string.Empty);
                
                // Save and publish changes to make the audio player visible on the live site
                contentService.SaveAndPublish(content);
            }
            else if (statusResponse.Status.StartsWith("error") || statusResponse.Status == "failed")
            {
                // Error happened during synthesis; clear the task id to avoid endless checking loops
                content.SetValue("voiceSyncTaskId", string.Empty);
                contentService.Save(content);
            }
        }

        private async Task<StatusResponse> CheckTaskStatusAsync(string taskId, CancellationToken ct)
        {
            try
            {
                var apiUrl = _configuration["VoiceSync:ApiUrl"] ?? "http://localhost:8000";
                var apiKey = _configuration["VoiceSync:ApiKey"];

                using var client = _httpClientFactory.CreateClient();
                client.BaseAddress = new Uri(apiUrl);

                if (!string.IsNullOrEmpty(apiKey))
                {
                    client.DefaultRequestHeaders.Add("X-API-Key", apiKey);
                }

                return await client.GetFromJsonAsync<StatusResponse>($"/status/{Uri.EscapeDataString(taskId)}", ct);
            }
            catch (Exception)
            {
                return null;
            }
        }
    }
}
