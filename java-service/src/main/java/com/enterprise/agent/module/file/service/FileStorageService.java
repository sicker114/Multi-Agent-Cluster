package com.enterprise.agent.module.file.service;

import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;

/**
 * 文件存储策略接口。实现类：本地存储 / MinIO 存储。
 *
 * @author enterprise-agent
 */
public interface FileStorageService {

    /**
     * 存储文件。
     *
     * @param file     上传文件
     * @param objectKey 目标对象键（相对路径）
     * @return 实际存储路径 / 对象键
     */
    String store(MultipartFile file, String objectKey);

    /**
     * 读取文件输入流。
     *
     * @param storagePath 存储路径 / 对象键
     * @return 输入流
     */
    InputStream read(String storagePath);

    /**
     * 删除文件。
     *
     * @param storagePath 存储路径 / 对象键
     */
    void delete(String storagePath);

    /** 存储类型标识：local / minio。 */
    String storageType();
}
