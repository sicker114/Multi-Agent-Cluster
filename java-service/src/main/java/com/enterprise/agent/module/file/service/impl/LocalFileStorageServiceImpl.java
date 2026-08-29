package com.enterprise.agent.module.file.service.impl;

import cn.hutool.core.io.FileUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.module.file.service.FileStorageService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 本地文件存储实现。默认启用（enterprise.file.storage-type=local）。
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "enterprise.file.storage-type", havingValue = "local", matchIfMissing = true)
public class LocalFileStorageServiceImpl implements FileStorageService {

    private final EnterpriseProperties properties;

    @Override
    public String store(MultipartFile file, String objectKey) {
        try {
            Path root = Paths.get(properties.getFile().getLocalPath()).toAbsolutePath();
            Path target = root.resolve(objectKey).normalize();
            // 防止路径穿越
            if (!target.startsWith(root)) {
                throw new BusinessException(ResultCode.FILE_UPLOAD_FAILED, "非法文件路径");
            }
            FileUtil.mkParentDirs(target.toFile());
            file.transferTo(target.toFile());
            log.info("本地存储文件成功 path={}", target);
            return objectKey;
        } catch (Exception e) {
            log.error("本地存储文件失败", e);
            throw new BusinessException(ResultCode.FILE_UPLOAD_FAILED, e.getMessage());
        }
    }

    @Override
    public InputStream read(String storagePath) {
        try {
            Path root = Paths.get(properties.getFile().getLocalPath()).toAbsolutePath();
            Path target = root.resolve(storagePath).normalize();
            File f = target.toFile();
            if (!f.exists()) {
                throw new BusinessException(ResultCode.FILE_NOT_FOUND);
            }
            return Files.newInputStream(target);
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            throw new BusinessException(ResultCode.FILE_READ_FAILED, e.getMessage());
        }
    }

    @Override
    public void delete(String storagePath) {
        Path root = Paths.get(properties.getFile().getLocalPath()).toAbsolutePath();
        Path target = root.resolve(storagePath).normalize();
        FileUtil.del(target.toFile());
    }

    @Override
    public String storageType() {
        return "local";
    }
}
