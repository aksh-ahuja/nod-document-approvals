import { ArrowRight, Check, FileText, UserRound } from 'lucide-react'
import { Logo } from '../components/ui'

export function Landing({ signedIn, demo }: { signedIn: boolean; demo: boolean }) {
  return (
    <div className="landing">
      <header className="landing-nav">
        <Logo inverse />
        <span className="landing-descriptor">A little nod. A big next step.</span>
        <a className="button landing-login" href={signedIn ? '#/app' : '#/login'}>
          {signedIn ? 'Open workspace' : 'Log in'} <ArrowRight size={16} />
        </a>
      </header>
      <main id="main-content" className="landing-main">
        <section className="hero" aria-labelledby="hero-title">
          <span className="hero-label">DOCUMENT APPROVALS, SIMPLIFIED</span>
          <h1 id="hero-title">
            Give good work
            <br />
            <span>
              the green light
              <sup>
                {' '}
                <Check aria-hidden="true" />
              </sup>
              .
            </span>
          </h1>
          <p>Send a document. Pick a reviewer. Get a clear decision.</p>
          <a className="button hero-cta" href={signedIn ? '#/app' : '#/register'}>
            {signedIn ? 'Open workspace' : 'Get started'} <ArrowRight size={19} />
          </a>
          {demo && !signedIn && (
            <a className="hero-demo" href="#/login?demo">
              Or take a look around <ArrowRight size={13} />
            </a>
          )}
        </section>
        <section className="landing-flow" aria-label="How Nod works">
          <div className="flow-lead">
            <span>
              FROM DRAFT
              <br />
              TO DECISION.
            </span>
            <ArrowRight size={23} aria-hidden="true" />
          </div>
          <div className="flow-step">
            <span className="flow-number">01</span>
            <FileText size={19} aria-hidden="true" />
            <h2>Add your document</h2>
          </div>
          <div className="flow-step">
            <span className="flow-number">02</span>
            <UserRound size={19} aria-hidden="true" />
            <h2>Choose your reviewer</h2>
          </div>
          <div className="flow-step">
            <span className="flow-number">03</span>
            <Check size={19} aria-hidden="true" />
            <h2>Keep the decision</h2>
          </div>
        </section>
      </main>
      <footer className="landing-footer">
        <span>Less back-and-forth. More forward.</span>
        <span>Made for work that moves.</span>
      </footer>
    </div>
  )
}
