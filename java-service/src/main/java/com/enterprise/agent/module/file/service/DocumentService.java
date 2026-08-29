package com.enterprise.agent.module.file.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.entity.BizDocument;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * 文档知识库服务接口。
 *
 * @author enterprise-agent
 */
public interface DocumentService {

    /**
     * 上传文档：存储文件 + 落库元数据。
     *
     * @param file     上传文件
     * @param category 文档分类
     * @return 文档元数据
     */
    BizDocument upload(MultipartFile file, String category);

    /**
     * 分页查询当前用户数据范围内的文档。
     */
    Page<BizDocument> pageList(long pageNo, long pageSize, String keyword);

    /**
     * 删除文档（逻辑删除 + 物理删除文件）。
     */
    void delete(Long docId);

    /**
     * 供 Python GraphRAG 拉取文档正文（已脱敏）。
     *
     * @param docId 文档ID
     * @return 包含 docId、fileName、category、脱敏后 content 的 Map
     */
    Map<String, Object> readContentForAgent(Long docId);

    /**
     * 供 Python 列出某部门范围内的可索引文档清单。
     *
     * @param deptId 部门ID
     * @return 文档清单
     */
    List<Map<String, Object>> listDocsForAgent(Long deptId);
}
