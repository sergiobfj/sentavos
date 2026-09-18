import { useEffect, useRef, type ReactNode } from "react";

/** Confirmação de ação destrutiva.
 *
 * Substituiu o `confirm()` do navegador, que tinha três problemas: aparece com
 * a cara do sistema no meio de um app que não parece com ele, escreve o texto
 * numa linha só ("Excluir Fone de Ouvido?") sem dizer o que mais vai embora, e
 * no iOS abre com o botão de confirmar no lado do polegar.
 *
 * Aqui a confirmação é dupla no sentido que importa: não é clicar duas vezes na
 * mesma coisa, é **ver o que vai sumir** e só então tocar num botão diferente
 * do que abriu o diálogo. O que está em risco vem por escrito — o nome do item
 * e as consequências ("7 saldos vão junto") — porque é isso que faz a pessoa
 * parar, não um segundo clique no mesmo lugar.
 *
 * O foco nasce em "Cancelar" de propósito: quem apertou por engano e deu Enter
 * cancela, não confirma.
 */
export default function ConfirmDialog({
  title,
  itemName,
  consequences = [],
  confirmLabel = "Excluir",
  pending = false,
  error,
  onConfirm,
  onCancel,
  children,
}: {
  title: string;
  /** O que vai sumir, com o nome que a pessoa deu. Aparece em destaque. */
  itemName?: string;
  /** O que mais vai junto. Uma frase por item — vazio quando não há nada. */
  consequences?: string[];
  confirmLabel?: string;
  pending?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  /** Espaço pra escolha extra, como "mover os lançamentos para". */
  children?: ReactNode;
}) {
  const cancelarRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelarRef.current?.focus();
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", aoTeclar);

    // Sem isso a página de trás rola junto com o dedo no diálogo.
    //
    // Restaura o valor ANTERIOR, e não "": este diálogo quase sempre abre de
    // dentro de outro modal, que já travou a rolagem. Limpando no cego, o
    // cancelar aqui destravava a página por baixo do formulário que continuou
    // aberto — e aí a tela de trás rolava sozinha ao arrastar no modal.
    const travaAnterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", aoTeclar);
      document.body.style.overflow = travaAnterior;
    };
  }, [onCancel]);

  return (
    // O overlay fecha no toque de fora, e fechar fora sempre cancela: num
    // diálogo destrutivo, o gesto ambíguo tem que cair no lado seguro.
    //
    // z-index acima do .overlay padrão (70), não abaixo: este diálogo nasce
    // dentro do modal de edição, então empatar ou ficar abaixo o esconderia
    // atrás do formulário que o abriu — a confirmação existiria e ninguém
    // veria.
    <div className="overlay" style={{ zIndex: 80 }} onMouseDown={onCancel}>
      <div
        className="modal modal-confirm"
        onMouseDown={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="m-body confirm-body">
          <div className="confirm-icone" aria-hidden>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
              <path d="M3 6h18M8 6V4.2A1.2 1.2 0 0 1 9.2 3h5.6A1.2 1.2 0 0 1 16 4.2V6" />
              <path d="M5.5 6l1 13.2A1.8 1.8 0 0 0 8.3 21h7.4a1.8 1.8 0 0 0 1.8-1.8L18.5 6" />
              <path d="M10 10.5v6M14 10.5v6" />
            </svg>
          </div>

          <h3 className="confirm-titulo">{title}</h3>
          {itemName && <div className="confirm-item">{itemName}</div>}

          {consequences.length > 0 && (
            <ul className="confirm-conseq">
              {consequences.map((frase, i) => (
                <li key={i}>{frase}</li>
              ))}
            </ul>
          )}

          <p className="confirm-aviso">Não tem como desfazer.</p>

          {children}

          {error && (
            <div className="error-box" style={{ padding: 0, textAlign: "left", marginTop: "var(--s3)" }}>
              {error}
            </div>
          )}
        </div>

        <div className="m-foot">
          <button ref={cancelarRef} type="button" className="btn" onClick={onCancel} disabled={pending}>
            Cancelar
          </button>
          <button type="button" className="btn btn-danger-solid" onClick={onConfirm} disabled={pending}>
            {pending ? "Excluindo…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
