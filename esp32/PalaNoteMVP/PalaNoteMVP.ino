
#include <Arduino.h>
#include "driver/i2s.h"

// Pala Note - INMP441 Microphone Test

#define I2S_PORT I2S_NUM_0

#define PIN_I2S_BCLK 26  // INMP441 SCK
#define PIN_I2S_WS   25  // INMP441 WS
#define PIN_I2S_SD   33  // INMP441 SD

#define SAMPLE_RATE 16000
#define BUFFER_SIZE 512

int32_t samples[BUFFER_SIZE];

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==============================");
  Serial.println(" PALA NOTE - MIC TEST");
  Serial.println("==============================");

  // I2S configuration
  i2s_config_t config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  // I2S pin configuration
  i2s_pin_config_t pinConfig = {
    .bck_io_num = PIN_I2S_BCLK,
    .ws_io_num = PIN_I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = PIN_I2S_SD,
    .mck_io_num = I2S_PIN_NO_CHANGE
  };

  // Install I2S driver
  esp_err_t result = i2s_driver_install(
    I2S_PORT, &config, 0, NULL
  );

  if (result != ESP_OK) {
    Serial.printf("I2S driver installation failed: %d\n", result);
    while (true) delay(1000);
  }

  // Assign pins
  result = i2s_set_pin(I2S_PORT, &pinConfig);

  if (result != ESP_OK) {
    Serial.printf("I2S pin setup failed: %d\n", result);
    while (true) delay(1000);
  }

  // Set clock
  i2s_set_clk(
    I2S_PORT,
    SAMPLE_RATE,
    I2S_BITS_PER_SAMPLE_32BIT,
    I2S_CHANNEL_MONO
  );

  Serial.println("I2S initialized successfully!");
  Serial.println("Speak or tap near the microphone...");
  Serial.println();
}

void loop() {
  size_t bytesRead = 0;

  // Read microphone data
  esp_err_t result = i2s_read(
    I2S_PORT,
    samples,
    sizeof(samples),
    &bytesRead,
    portMAX_DELAY
  );

  if (result == ESP_OK && bytesRead > 0) {
    int count = bytesRead / sizeof(int32_t);

    int64_t sum = 0;
    int32_t peak = 0;

    for (int i = 0; i < count; i++) {
      // INMP441 data is packed in a 32-bit I2S slot.
      int32_t sample = samples[i] >> 14;

      if (sample < 0) sample = -sample;

      if (sample > peak) {
        peak = sample;
      }

      sum += (int64_t)sample * sample;
    }

    float rms = 0;

    if (count > 0) {
      rms = sqrt((double)sum / count);
    }

    Serial.print("Peak: ");
    Serial.print(peak);
    Serial.print(" | RMS: ");
    Serial.println(rms, 2);
  }
}
