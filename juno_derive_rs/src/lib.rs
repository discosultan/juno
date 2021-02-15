use proc_macro::TokenStream;

mod macros;
mod util;

#[proc_macro_derive(ChromosomeEnum)]
pub fn derive_chromosome_enum(input: TokenStream) -> TokenStream {
    macros::derive_chromosome_enum(input)
}

#[proc_macro_derive(Chromosome, attributes(chromosome))]
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    macros::derive_chromosome(input)
}

#[proc_macro_derive(Signal)]
pub fn derive_signal(input: TokenStream) -> TokenStream {
    macros::derive_signal(input)
}
