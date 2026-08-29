package com.enterprise.agent.module.file.service.impl;

import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.common.utils.DesensitizeUtil;
import com.enterprise.agent.common.utils.DocumentExtractUtil;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.entity.BizDocument;
import com.enterprise.agent.mapper.BizDocumentMapper;
import com.enterprise.agent.module.file.service.DocumentService;
import com.enterprise.agent.module.file.service.FileStorageService;
import com.enterprise.agent.security.LoginUser;
import com.enterprise.agent.security.SecurityUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 文档知识库服务实现：上传、分页、删除，以及供 Python 拉取的脱敏正文接口。
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DocumentServiceImpl implements DocumentService {

    private final BizDocumentMapper documentMapper;
    private final FileStorageService fileStorageService;
    private final EnterpriseProperties properties;
    private final RagIndexNotifier ragIndexNotifier;

    @Override
    public BizDocument upload(MultipartFile file, String category) {
        if (file == null || file.isEmpty()) {
            throw new BusinessException(ResultCode.FILE_EMPTY);
        }
        String originalName = file.getOriginalFilename();
        String ext = FileUtil.extName(originalName);
        if (StrUtil.isBlank(ext)) {
            throw new BusinessException(ResultCode.FILE_TYPE_NOT_SUPPORT);
        }
        List<String> allow = Arrays.stream(properties.getFile().getAllowExtensions().split(","))
                .map(String::trim).map(String::toLowerCase).collect(Collectors.toList());
        if (!allow.contains(ext.toLowerCase())) {
            throw new BusinessException(ResultCode.FILE_TYPE_NOT_SUPPORT,
                    "仅支持：" + properties.getFile().getAllowExtensions());
        }

        LoginUser user = SecurityUtil.currentUser();
        // 对象键：按部门/日期/uuid 组织，避免同名冲突
        String objectKey = StrUtil.format("dept_{}/{}/{}.{}",
                user.getDeptId(), LocalDate.now(), IdUtil.fastSimpleUUID(), ext);
        fileStorageService.store(file, objectKey);

        BizDocument doc = new BizDocument();
        doc.setFileName(originalName);
        doc.setFileType(ext.toLowerCase());
        doc.setStorageType(fileStorageService.storageType());
        doc.setStoragePath(objectKey);
        doc.setCategory(StrUtil.blankToDefault(category, "通用"));
        doc.setDeptId(user.getDeptId());
        doc.setUploaderId(user.getUserId());
        doc.setUploaderName(user.getUser().getRealName());
        doc.setFileSize(file.getSize());
        doc.setIndexed(0);
        documentMapper.insert(doc);
        log.info("文档上传成功 id={} name={} dept={}", doc.getId(), originalName, user.getDeptId());
        if (properties.getFile().isAutoIndexOnUpload()) {
            ragIndexNotifier.notifyIndex(doc.getId(), doc.getDeptId());
        }
        return doc;
    }

    @Override
    public Page<BizDocument> pageList(long pageNo, long pageSize, String keyword) {
        LambdaQueryWrapper<BizDocument> wrapper = new LambdaQueryWrapper<>();
        // 数据权限：普通用户仅本部门文档
        List<Long> deptIds = SecurityUtil.dataScopeDeptIds();
        if (deptIds != null) {
            wrapper.in(BizDocument::getDeptId, deptIds);
        }
        if (StrUtil.isNotBlank(keyword)) {
            wrapper.like(BizDocument::getFileName, keyword);
        }
        wrapper.orderByDesc(BizDocument::getCreateTime);
        return documentMapper.selectPage(new Page<>(pageNo, pageSize), wrapper);
    }

    @Override
    public void delete(Long docId) {
        BizDocument doc = documentMapper.selectById(docId);
        if (doc == null) {
            throw new BusinessException(ResultCode.FILE_NOT_FOUND);
        }
        // 越权校验：不能删除非本部门文档
        SecurityUtil.checkDataScope(doc.getDeptId());
        fileStorageService.delete(doc.getStoragePath());
        documentMapper.deleteById(docId);
        ragIndexNotifier.notifyDelete(docId);
        log.info("文档删除成功 id={}", docId);
    }

    @Override
    public Map<String, Object> readContentForAgent(Long docId) {
        BizDocument doc = documentMapper.selectById(docId);
        if (doc == null) {
            throw new BusinessException(ResultCode.FILE_NOT_FOUND);
        }
        String rawText = DocumentExtractUtil.extract(
                fileStorageService.read(doc.getStoragePath()), doc.getFileType());
        // 关键：返回给 Python 前统一脱敏，防止敏感信息外泄
        String safeText = DesensitizeUtil.desensitizeText(rawText);

        Map<String, Object> result = new HashMap<>(8);
        result.put("docId", doc.getId());
        result.put("fileName", doc.getFileName());
        result.put("category", doc.getCategory());
        result.put("deptId", doc.getDeptId());
        result.put("content", safeText);
        return result;
    }

    @Override
    public List<Map<String, Object>> listDocsForAgent(Long deptId) {
        LambdaQueryWrapper<BizDocument> wrapper = new LambdaQueryWrapper<BizDocument>()
                .eq(deptId != null, BizDocument::getDeptId, deptId)
                .orderByDesc(BizDocument::getCreateTime);
        return documentMapper.selectList(wrapper).stream().map(doc -> {
            Map<String, Object> m = new HashMap<>(6);
            m.put("docId", doc.getId());
            m.put("fileName", doc.getFileName());
            m.put("fileType", doc.getFileType());
            m.put("category", doc.getCategory());
            m.put("deptId", doc.getDeptId());
            m.put("indexed", doc.getIndexed());
            return m;
        }).collect(Collectors.toList());
    }
}
