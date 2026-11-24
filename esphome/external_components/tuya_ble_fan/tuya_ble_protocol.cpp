#include "tuya_ble_protocol.h"

#include <algorithm>
#include <cstring>

#ifdef TUYA_BLE_HOST_TEST
#include <openssl/evp.h>
#else
#include <mbedtls/aes.h>
#include <mbedtls/md5.h>
#include <mbedtls/version.h>
#endif

namespace esphome {
namespace tuya_ble_fan {

TuyaDp TuyaDp::make_bool(uint8_t id, bool v) {
  TuyaDp dp;
  dp.id = id;
  dp.type = TuyaDpType::BOOL;
  dp.value = {static_cast<uint8_t>(v ? 1 : 0)};
  return dp;
}

TuyaDp TuyaDp::make_int(uint8_t id, int32_t v) {
  TuyaDp dp;
  dp.id = id;
  dp.type = TuyaDpType::INT;
  uint32_t u = static_cast<uint32_t>(v);
  dp.value = {
      static_cast<uint8_t>((u >> 24) & 0xFF),
      static_cast<uint8_t>((u >> 16) & 0xFF),
      static_cast<uint8_t>((u >> 8) & 0xFF),
      static_cast<uint8_t>(u & 0xFF),
  };
  return dp;
}

TuyaDp TuyaDp::make_enum(uint8_t id, uint8_t v) {
  TuyaDp dp;
  dp.id = id;
  dp.type = TuyaDpType::ENUM;
  dp.value = {v};
  return dp;
}

bool TuyaDp::as_bool() const {
  return !value.empty() && value[0] != 0;
}

int32_t TuyaDp::as_int() const {
  if (value.empty()) return 0;
  uint32_t u = 0;
  for (uint8_t b : value) {
    u = (u << 8) | b;
  }
  return static_cast<int32_t>(u);
}

uint8_t TuyaDp::as_enum() const {
  return value.empty() ? 0 : value[0];
}

uint16_t crc16_modbus(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= static_cast<uint16_t>(data[i]);
    for (int bit = 0; bit < 8; bit++) {
      if (crc & 0x0001) {
        crc = (crc >> 1) ^ 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

void md5_hash(const uint8_t *data, size_t len, uint8_t out[16]) {
#ifdef TUYA_BLE_HOST_TEST
  unsigned int out_len = 0;
  EVP_Digest(data, len, out, &out_len, EVP_md5(), nullptr);
#else
#if defined(MBEDTLS_VERSION_NUMBER) && (MBEDTLS_VERSION_NUMBER >= 0x03000000)
  mbedtls_md5(data, len, out);
#else
  mbedtls_md5_ret(data, len, out);
#endif
#endif
}

bool aes128_cbc_encrypt(const uint8_t key[16], const uint8_t iv[16],
                        const uint8_t *in, size_t in_len,
                        std::vector<uint8_t> &out) {
  // Tuya BLE pads plaintext with 0x00 to a multiple of 16 bytes
  size_t padded_len = ((in_len + 15) / 16) * 16;
  if (padded_len == 0) padded_len = 16;
  std::vector<uint8_t> padded(padded_len, 0);
  if (in_len > 0 && in != nullptr) {
    std::memcpy(padded.data(), in, in_len);
  }
  out.resize(padded_len);

#ifdef TUYA_BLE_HOST_TEST
  EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
  if (!ctx) return false;
  int len1 = 0, len2 = 0;
  bool ok = EVP_EncryptInit_ex(ctx, EVP_aes_128_cbc(), nullptr, key, iv) == 1 &&
            EVP_CIPHER_CTX_set_padding(ctx, 0) == 1 &&
            EVP_EncryptUpdate(ctx, out.data(), &len1, padded.data(), static_cast<int>(padded_len)) == 1 &&
            EVP_EncryptFinal_ex(ctx, out.data() + len1, &len2) == 1;
  EVP_CIPHER_CTX_free(ctx);
  return ok;
#else
  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  uint8_t iv_copy[16];
  std::memcpy(iv_copy, iv, 16);
  int ret = mbedtls_aes_setkey_enc(&aes, key, 128);
  if (ret == 0) {
    ret = mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_ENCRYPT, padded_len, iv_copy, padded.data(), out.data());
  }
  mbedtls_aes_free(&aes);
  return ret == 0;
#endif
}

bool aes128_cbc_decrypt(const uint8_t key[16], const uint8_t iv[16],
                        const uint8_t *in, size_t in_len,
                        std::vector<uint8_t> &out) {
  if (in == nullptr || in_len == 0 || (in_len % 16) != 0) {
    return false;
  }
  out.resize(in_len);

#ifdef TUYA_BLE_HOST_TEST
  EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
  if (!ctx) return false;
  int len1 = 0, len2 = 0;
  bool ok = EVP_DecryptInit_ex(ctx, EVP_aes_128_cbc(), nullptr, key, iv) == 1 &&
            EVP_CIPHER_CTX_set_padding(ctx, 0) == 1 &&
            EVP_DecryptUpdate(ctx, out.data(), &len1, in, static_cast<int>(in_len)) == 1 &&
            EVP_DecryptFinal_ex(ctx, out.data() + len1, &len2) == 1;
  EVP_CIPHER_CTX_free(ctx);
  return ok;
#else
  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  uint8_t iv_copy[16];
  std::memcpy(iv_copy, iv, 16);
  int ret = mbedtls_aes_setkey_dec(&aes, key, 128);
  if (ret == 0) {
    ret = mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_DECRYPT, in_len, iv_copy, in, out.data());
  }
  mbedtls_aes_free(&aes);
  return ret == 0;
#endif
}

void derive_login_key(const std::string &local_key, uint8_t out_key[16]) {
  size_t prefix_len = std::min<size_t>(local_key.size(), 6);
  md5_hash(reinterpret_cast<const uint8_t *>(local_key.data()), prefix_len, out_key);
}

void derive_session_key(const std::string &local_key, const uint8_t srand[6], uint8_t out_key[16]) {
  uint8_t buf[12] = {0};
  size_t prefix_len = std::min<size_t>(local_key.size(), 6);
  std::memcpy(buf, local_key.data(), prefix_len);
  std::memcpy(buf + 6, srand, 6);
  md5_hash(buf, 12, out_key);
}

void append_varint(std::vector<uint8_t> &out, uint32_t value) {
  do {
    uint8_t b = static_cast<uint8_t>(value & 0x7F);
    value >>= 7;
    if (value != 0) b |= 0x80;
    out.push_back(b);
  } while (value != 0);
}

bool read_varint(const uint8_t *data, size_t len, size_t &pos, uint32_t &out) {
  out = 0;
  uint32_t shift = 0;
  while (pos < len) {
    uint8_t b = data[pos++];
    out |= static_cast<uint32_t>(b & 0x7F) << shift;
    if ((b & 0x80) == 0) return true;
    shift += 7;
    if (shift >= 28) return false;
  }
  return false;
}

std::vector<uint8_t> build_encrypted_packet(uint32_t seq_num, uint32_t response_to,
                                            uint16_t code, const std::vector<uint8_t> &payload,
                                            uint8_t security_flag, const uint8_t key[16],
                                            const uint8_t iv[16]) {
  std::vector<uint8_t> plain;
  plain.reserve(14 + payload.size());

  // seq_num (4B BE)
  plain.push_back(static_cast<uint8_t>((seq_num >> 24) & 0xFF));
  plain.push_back(static_cast<uint8_t>((seq_num >> 16) & 0xFF));
  plain.push_back(static_cast<uint8_t>((seq_num >> 8) & 0xFF));
  plain.push_back(static_cast<uint8_t>(seq_num & 0xFF));

  // response_to (4B BE)
  plain.push_back(static_cast<uint8_t>((response_to >> 24) & 0xFF));
  plain.push_back(static_cast<uint8_t>((response_to >> 16) & 0xFF));
  plain.push_back(static_cast<uint8_t>((response_to >> 8) & 0xFF));
  plain.push_back(static_cast<uint8_t>(response_to & 0xFF));

  // code (2B BE)
  plain.push_back(static_cast<uint8_t>((code >> 8) & 0xFF));
  plain.push_back(static_cast<uint8_t>(code & 0xFF));

  // data_len (2B BE)
  uint16_t dlen = static_cast<uint16_t>(payload.size());
  plain.push_back(static_cast<uint8_t>((dlen >> 8) & 0xFF));
  plain.push_back(static_cast<uint8_t>(dlen & 0xFF));

  // data
  plain.insert(plain.end(), payload.begin(), payload.end());

  // crc16 (2B BE) over seq_num..data
  uint16_t crc = crc16_modbus(plain.data(), plain.size());
  plain.push_back(static_cast<uint8_t>((crc >> 8) & 0xFF));
  plain.push_back(static_cast<uint8_t>(crc & 0xFF));

  std::vector<uint8_t> cipher;
  if (!aes128_cbc_encrypt(key, iv, plain.data(), plain.size(), cipher)) {
    return {};
  }

  std::vector<uint8_t> packet;
  packet.reserve(1 + 16 + cipher.size());
  packet.push_back(security_flag);
  packet.insert(packet.end(), iv, iv + 16);
  packet.insert(packet.end(), cipher.begin(), cipher.end());
  return packet;
}

bool parse_encrypted_packet(const uint8_t *raw, size_t raw_len,
                            const uint8_t login_key[16], const uint8_t session_key[16],
                            bool has_session_key, TuyaDecryptedFrame &out) {
  if (raw == nullptr || raw_len < 1 + 16 + 16) {
    return false;
  }
  uint8_t security_flag = raw[0];
  const uint8_t *iv = raw + 1;
  const uint8_t *cipher = raw + 17;
  size_t cipher_len = raw_len - 17;
  if ((cipher_len % 16) != 0) {
    return false;
  }

  const uint8_t *key = nullptr;
  if (security_flag == SECURITY_FLAG_LOGIN) {
    key = login_key;
  } else if (security_flag == SECURITY_FLAG_SESSION && has_session_key) {
    key = session_key;
  } else {
    return false;
  }

  std::vector<uint8_t> plain;
  if (!aes128_cbc_decrypt(key, iv, cipher, cipher_len, plain) || plain.size() < 14) {
    return false;
  }

  uint32_t seq_num = (static_cast<uint32_t>(plain[0]) << 24) |
                     (static_cast<uint32_t>(plain[1]) << 16) |
                     (static_cast<uint32_t>(plain[2]) << 8) |
                     static_cast<uint32_t>(plain[3]);
  uint32_t response_to = (static_cast<uint32_t>(plain[4]) << 24) |
                         (static_cast<uint32_t>(plain[5]) << 16) |
                         (static_cast<uint32_t>(plain[6]) << 8) |
                         static_cast<uint32_t>(plain[7]);
  uint16_t code = (static_cast<uint16_t>(plain[8]) << 8) | static_cast<uint16_t>(plain[9]);
  uint16_t data_len = (static_cast<uint16_t>(plain[10]) << 8) | static_cast<uint16_t>(plain[11]);

  if (12u + data_len + 2u > plain.size()) {
    return false;
  }

  uint16_t expected_crc = (static_cast<uint16_t>(plain[12 + data_len]) << 8) |
                          static_cast<uint16_t>(plain[12 + data_len + 1]);
  uint16_t actual_crc = crc16_modbus(plain.data(), 12 + data_len);
  if (expected_crc != actual_crc) {
    return false;
  }

  out.seq_num = seq_num;
  out.response_to = response_to;
  out.code = code;
  out.data.assign(plain.begin() + 12, plain.begin() + 12 + data_len);
  return true;
}

std::vector<std::vector<uint8_t>> fragment_gatt_packet(const std::vector<uint8_t> &encrypted_packet,
                                                       uint8_t protocol_version,
                                                       size_t chunk_size) {
  std::vector<std::vector<uint8_t>> chunks;
  if (chunk_size < 4) chunk_size = 20;

  size_t offset = 0;
  uint32_t packet_num = 0;
  while (offset < encrypted_packet.size() || packet_num == 0) {
    std::vector<uint8_t> chunk;
    chunk.reserve(chunk_size);
    append_varint(chunk, packet_num);
    if (packet_num == 0) {
      append_varint(chunk, static_cast<uint32_t>(encrypted_packet.size()));
      chunk.push_back(static_cast<uint8_t>((protocol_version & 0x0F) << 4));
    }
    size_t avail = chunk_size > chunk.size() ? (chunk_size - chunk.size()) : 0;
    size_t take = std::min(avail, encrypted_packet.size() - offset);
    chunk.insert(chunk.end(), encrypted_packet.begin() + offset, encrypted_packet.begin() + offset + take);
    chunks.push_back(std::move(chunk));
    offset += take;
    packet_num++;
  }
  return chunks;
}

void GattPacketReassembler::reset() {
  buffer_.clear();
  expected_len_ = 0;
  expected_packet_ = 0;
  protocol_version_ = 3;
  in_progress_ = false;
}

bool GattPacketReassembler::feed(const uint8_t *data, size_t len,
                                 std::vector<uint8_t> &out, uint8_t &protocol_version) {
  if (data == nullptr || len == 0) return false;
  size_t pos = 0;
  uint32_t packet_num = 0;
  if (!read_varint(data, len, pos, packet_num)) {
    reset();
    return false;
  }

  if (packet_num == 0) {
    reset();
    uint32_t total_len = 0;
    if (!read_varint(data, len, pos, total_len) || pos >= len) {
      return false;
    }
    if (total_len == 0 || total_len > 2048) {
      return false;
    }
    protocol_version_ = (data[pos++] >> 4) & 0x0F;
    expected_len_ = total_len;
    expected_packet_ = 1;
    in_progress_ = true;
    buffer_.reserve(total_len);
  } else {
    if (!in_progress_ || packet_num != expected_packet_) {
      reset();
      return false;
    }
    expected_packet_++;
  }

  if (pos < len) {
    size_t remain = expected_len_ > buffer_.size() ? (expected_len_ - buffer_.size()) : 0;
    size_t copy_len = std::min(remain, len - pos);
    buffer_.insert(buffer_.end(), data + pos, data + pos + copy_len);
  }

  if (in_progress_ && buffer_.size() >= expected_len_) {
    out = std::move(buffer_);
    protocol_version = protocol_version_;
    reset();
    return true;
  }
  return false;
}

std::vector<uint8_t> build_pair_payload(const std::string &uuid, const std::string &local_key,
                                        const std::string &device_id) {
  // 16 bytes uuid + 6 bytes local_key[:6] + 22 bytes device_id = 44 bytes
  std::vector<uint8_t> out(44, 0);
  const std::string &effective_uuid = uuid.empty() ? device_id : uuid;
  std::memcpy(out.data(), effective_uuid.data(), std::min<size_t>(effective_uuid.size(), 16));
  std::memcpy(out.data() + 16, local_key.data(), std::min<size_t>(local_key.size(), 6));
  std::memcpy(out.data() + 22, device_id.data(), std::min<size_t>(device_id.size(), 22));
  return out;
}

bool parse_device_info_response(const std::vector<uint8_t> &data, TuyaDeviceInfoResponse &out) {
  if (data.size() < 12) return false;
  out.device_version_major = data[0];
  out.device_version_minor = data[1];
  out.protocol_version_major = data[2];
  out.protocol_version_minor = data[3];
  out.flag = data[4];
  out.is_bind = data[5] != 0;
  std::memcpy(out.srand, data.data() + 6, 6);
  return true;
}

std::vector<uint8_t> encode_dps_v3(const std::vector<TuyaDp> &dps) {
  std::vector<uint8_t> out;
  for (const auto &dp : dps) {
    out.push_back(dp.id);
    out.push_back(static_cast<uint8_t>(dp.type));
    out.push_back(static_cast<uint8_t>(dp.value.size()));
    out.insert(out.end(), dp.value.begin(), dp.value.end());
  }
  return out;
}

std::vector<uint8_t> encode_dps_v4(uint16_t dp_seq, const std::vector<TuyaDp> &dps) {
  std::vector<uint8_t> out;
  out.push_back(static_cast<uint8_t>((dp_seq >> 8) & 0xFF));
  out.push_back(static_cast<uint8_t>(dp_seq & 0xFF));
  out.push_back(0x00);  // flag
  for (const auto &dp : dps) {
    out.push_back(dp.id);
    out.push_back(static_cast<uint8_t>(dp.type));
    uint16_t vlen = static_cast<uint16_t>(dp.value.size());
    out.push_back(static_cast<uint8_t>((vlen >> 8) & 0xFF));
    out.push_back(static_cast<uint8_t>(vlen & 0xFF));
    out.insert(out.end(), dp.value.begin(), dp.value.end());
  }
  return out;
}

bool decode_dps_v3(const uint8_t *data, size_t len, std::vector<TuyaDp> &out) {
  out.clear();
  size_t pos = 0;
  while (pos + 3 <= len) {
    TuyaDp dp;
    dp.id = data[pos++];
    dp.type = static_cast<TuyaDpType>(data[pos++]);
    uint8_t vlen = data[pos++];
    if (pos + vlen > len) return false;
    dp.value.assign(data + pos, data + pos + vlen);
    pos += vlen;
    out.push_back(std::move(dp));
  }
  return pos == len;
}

bool decode_dps_v4(const uint8_t *data, size_t len, std::vector<TuyaDp> &out) {
  out.clear();
  size_t pos = 0;
  while (pos + 4 <= len) {
    TuyaDp dp;
    dp.id = data[pos++];
    dp.type = static_cast<TuyaDpType>(data[pos++]);
    uint16_t vlen = (static_cast<uint16_t>(data[pos]) << 8) | static_cast<uint16_t>(data[pos + 1]);
    pos += 2;
    if (pos + vlen > len) return false;
    dp.value.assign(data + pos, data + pos + vlen);
    pos += vlen;
    out.push_back(std::move(dp));
  }
  return pos == len;
}

bool match_tuya_advertisement(const uint8_t *service_data, size_t service_data_len,
                              const uint8_t *mfg_data, size_t mfg_data_len,
                              const std::string &product_id,
                              const std::string &device_id,
                              const std::string &local_key) {
  if (service_data == nullptr || service_data_len < 3) {
    return false;
  }

  // Service data for 0xFD50:
  // byte 0: frame_control
  // byte 1: version (hi nibble) | product_id_type (lo nibble)
  // bytes 2..: product_id (raw ASCII) or MD5(product_id) (16 bytes)
  const uint8_t *pid_bytes = service_data + 2;
  size_t pid_len = service_data_len - 2;

  bool product_matches = false;
  if (!product_id.empty()) {
    if (pid_len == product_id.size() && std::memcmp(pid_bytes, product_id.data(), pid_len) == 0) {
      product_matches = true;
    } else if (pid_len >= 16) {
      uint8_t pid_md5[16];
      md5_hash(reinterpret_cast<const uint8_t *>(product_id.data()), product_id.size(), pid_md5);
      if (std::memcmp(pid_bytes, pid_md5, 16) == 0) {
        product_matches = true;
      }
    }
  }

  // If manufacturer data (0x07D0) has 16-byte encrypted uuid/device_id, try matching it specifically
  // so multiple fans of the same product_id in the same range can be distinguished.
  if (mfg_data != nullptr && mfg_data_len >= 18 && !device_id.empty()) {
    // Key = MD5(service_data[2..]), IV = Key
    uint8_t key_iv[16];
    md5_hash(pid_bytes, pid_len, key_iv);
    std::vector<uint8_t> decrypted;
    if (aes128_cbc_decrypt(key_iv, key_iv, mfg_data + 2, 16, decrypted)) {
      size_t cmp_len = std::min<size_t>(device_id.size(), 16);
      if (std::memcmp(decrypted.data(), device_id.data(), cmp_len) == 0) {
        return true;
      }
    }
    // Also try login_key as key/iv (used by some bound Tuya BLE v4 firmware)
    if (!local_key.empty()) {
      uint8_t login_key[16];
      derive_login_key(local_key, login_key);
      if (aes128_cbc_decrypt(login_key, login_key, mfg_data + 2, 16, decrypted)) {
        size_t cmp_len = std::min<size_t>(device_id.size(), 16);
        if (std::memcmp(decrypted.data(), device_id.data(), cmp_len) == 0) {
          return true;
        }
      }
    }
  }

  // Fallback: if product_id matches and no mfg_data disambiguation failed above,
  // allow product_id match when mfg_data is absent.
  return product_matches && (mfg_data == nullptr || mfg_data_len < 18);
}

bool extract_tuya_v3_uuid(const uint8_t *service_data_a201, size_t service_data_len,
                          const uint8_t *mfg_data_07d0, size_t mfg_data_len,
                          std::string &out_uuid) {
  out_uuid.clear();
  if (service_data_a201 == nullptr || service_data_len < 17) return false;
  if (mfg_data_07d0 == nullptr || mfg_data_len < 22) return false;

  uint8_t key_iv[16];
  md5_hash(service_data_a201 + 1, 16, key_iv);

  std::vector<uint8_t> decrypted;
  if (!aes128_cbc_decrypt(key_iv, key_iv, mfg_data_07d0 + 6, 16, decrypted) || decrypted.size() < 16) {
    return false;
  }

  // Validate printable ASCII (Tuya UUIDs are 16-byte ASCII alphanumeric strings)
  for (size_t i = 0; i < 16; i++) {
    uint8_t c = decrypted[i];
    if (c < 0x20 || c > 0x7E) {
      return false;
    }
  }
  out_uuid.assign(reinterpret_cast<const char *>(decrypted.data()), 16);
  return true;
}

}  // namespace tuya_ble_fan
}  // namespace esphome
