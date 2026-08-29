# ==========================================================
# Java 主服务 Dockerfile（多阶段构建）
# 构建产物：enterprise-agent-service.jar（pom 中 finalName 固定）
# ==========================================================

# ---------- 构建阶段 ----------
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /build
# 先复制 pom 以利用依赖缓存
COPY pom.xml .
RUN mvn -B dependency:go-offline
# 复制源码并打包（跳过测试加速镜像构建）
COPY src ./src
RUN mvn -B clean package -DskipTests

# ---------- 运行阶段 ----------
FROM eclipse-temurin:17-jre
LABEL maintainer="enterprise-agent"
WORKDIR /app

# 复制可执行 jar
COPY --from=builder /build/target/enterprise-agent-service.jar app.jar

# 运行期目录：文件上传与日志
RUN mkdir -p /app/upload-files /app/logs

EXPOSE 8080

# JVM 参数与时区
ENV TZ=Asia/Shanghai \
    JAVA_OPTS="-Xms512m -Xmx1024m -XX:+UseG1GC"

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
