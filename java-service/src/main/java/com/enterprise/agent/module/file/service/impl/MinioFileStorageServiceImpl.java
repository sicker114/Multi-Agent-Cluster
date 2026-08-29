package com.enterprise.agent.module.file.service.impl;

import cn.hutool.core.io.IoUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.module.file.service.FileStorageService;
import io.minio.*;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;

/**
 * MinIO 文件存储实现。启用条件：enterprise.file.storage-type=minio。
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "enterprise.file.storage-type", havingValue = "minio")
public class MinioFileStorageServiceImpl implements FileStorageService {

    private final EnterpriseProperties properties;
    private MinioClient client;

    @PostConstruct
    public void init() {
        EnterpriseProperties.FileConf.Minio conf = properties.getFile().getMinio();
        this.client = MinioClient.builder()
                .endpoint(conf.getEndpoint())
                .credentials(conf.getAccessKey(), conf.getSecretKey())
                .build();
        try {
            boolean exists = client.bucketExists(
                    BucketExistsArgs.builder().bucket(conf.getBucket()).build());
            if (!exists) {
                client.makeBucket(MakeBucketArgs.builder().bucket(conf.getBucket()).build());
                log.info("创建 MinIO 桶 {}", conf.getBucket());
            }
        } catch (Exception e) {
            log.error("初始化 MinIO 失败", e);
            throw new BusinessException(ResultCode.SYSTEM_ERROR, "MinIO 初始化失败");
        }
    }

    @Override
    public String store(MultipartFile file, String objectKey) {
        try (InputStream in = file.getInputStream()) {
            client.putObject(PutObjectArgs.builder()
                    .bucket(properties.getFile().getMinio().getBucket())
                    .object(objectKey)
                    .stream(in, file.getSize(), -1)
                    .contentType(file.getContentType())
                    .build());
            log.info("MinIO 存储文件成功 object={}", objectKey);
            return objectKey;
        } catch (Exception e) {
            log.error("MinIO 存储文件失败", e);
            throw new BusinessException(ResultCode.FILE_UPLOAD_FAILED, e.getMessage());
        }
    }

    @Override
    public InputStream read(String storagePath) {
        try {
            // 全量读取为字节数组再包装，避免连接未关闭
            GetObjectResponse resp = client.getObject(GetObjectArgs.builder()
                    .bucket(properties.getFile().getMinio().getBucket())
                    .object(storagePath)
                    .build());
            byte[] bytes = IoUtil.readBytes(resp);
            return IoUtil.toStream(bytes);
        } catch (Exception e) {
            throw new BusinessException(ResultCode.FILE_READ_FAILED, e.getMessage());
        }
    }

    @Override
    public void delete(String storagePath) {
        try {
            client.removeObject(RemoveObjectArgs.builder()
                    .bucket(properties.getFile().getMinio().getBucket())
                    .object(storagePath)
                    .build());
        } catch (Exception e) {
            log.warn("MinIO 删除文件失败 object={} err={}", storagePath, e.getMessage());
        }
    }

    @Override
    public String storageType() {
        return "minio";
    }
}
