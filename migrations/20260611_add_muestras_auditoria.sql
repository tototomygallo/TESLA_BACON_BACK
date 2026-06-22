IF OBJECT_ID(N'dbo.muestras_auditoria', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.muestras_auditoria (
        id int IDENTITY(1,1) NOT NULL,
        protocolo nvarchar(255) NULL,
        codigo nvarchar(255) NULL,
        tipo_estudio varchar(20) NULL,
        accion varchar(80) NOT NULL,
        usuario_id nvarchar(255) NULL,
        estado_anterior varchar(40) NULL,
        estado_nuevo varchar(40) NULL,
        detalle nvarchar(max) NULL,
        datos nvarchar(max) NULL,
        fecha datetime NOT NULL CONSTRAINT DF_muestras_auditoria_fecha DEFAULT (GETDATE()),
        CONSTRAINT PK_muestras_auditoria PRIMARY KEY (id)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_muestras_auditoria_protocolo'
      AND object_id = OBJECT_ID(N'dbo.muestras_auditoria')
)
BEGIN
    CREATE INDEX IX_muestras_auditoria_protocolo
        ON dbo.muestras_auditoria(protocolo, fecha);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_muestras_auditoria_codigo'
      AND object_id = OBJECT_ID(N'dbo.muestras_auditoria')
)
BEGIN
    CREATE INDEX IX_muestras_auditoria_codigo
        ON dbo.muestras_auditoria(codigo, fecha);
END;
